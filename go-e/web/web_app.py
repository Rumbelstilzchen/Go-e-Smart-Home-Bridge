"""
FastAPI Web Application for Go-e Smart Home Bridge.
Provides REST API and web interface for charger control and monitoring.
"""

import logging
import os
import time
from datetime import datetime, UTC
from typing import Optional
from pathlib import Path
from collections import defaultdict

from fastapi import FastAPI,Depends, Header, HTTPException, status, Cookie, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel
import yaml
from web.auth import AuthManager
from web.override_manager import OverrideManager
import uvicorn
import threading
import asyncio


# Setup logging
logger = logging.getLogger(__name__)

# ==================== Models ====================

class LoginRequest(BaseModel):
    username: str
    password: str

class OverrideRequest(BaseModel):
    end_time: str  # ISO format datetime
    start_time: Optional[str] = None

class ModeRequest(BaseModel):
    mode: str  # BASIC or ECO

# ==================== Global State ====================

app = FastAPI(title="Go-e Smart Home Bridge", version="1.0")
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

_exchange_data: dict  = {}
_auth_manager: AuthManager | None = None
_override_manager: OverrideManager | None = None
_web_config: dict | None = None
_uvicorn_server: uvicorn.Server | None = None
_server_thread: threading.Thread | None = None

# Rate limiting for login attempts
_login_attempts: dict = defaultdict(list)  # IP -> [timestamps]
_login_lock = threading.Lock()
MAX_LOGIN_ATTEMPTS = 5
LOGIN_ATTEMPT_WINDOW = 300  # 5 minutes

async def start_server(exchange_data):
    """Initialize application components."""
    global _exchange_data, _web_config, _auth_manager, _override_manager, _uvicorn_server, _server_thread

    # Thread-safe initialization

    _exchange_data = exchange_data
    _web_config = _exchange_data.get("web", {})

    _auth_manager = AuthManager(_web_config.get("auth", {}))
    _override_manager = OverrideManager(_exchange_data)

    # Add TrustedHost middleware for reverse proxy
    host = _web_config.get('host', '0.0.0.0')
    port = _web_config.get('port', 80)

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=_web_config.get("trusted_hosts", ["*"])  # Configure in config.yaml
    )
    # Configure CORS with web config
    allowed_origins = [
        "http://localhost",
        "http://localhost:80",
        f"http://localhost:{port}",
        "http://127.0.0.1",
        "http://127.0.0.1:80",
        f"http://127.0.0.1:{port}",
    ]
    cors_config = _web_config.get("cors", {})
    if cors_config.get("allowed_origins"):
        allowed_origins.extend(cors_config.get("allowed_origins", []))

    # Update CORS middleware
    for middleware in app.user_middleware:
        if middleware.cls == CORSMiddleware:
            middleware.options["allow_origins"] = allowed_origins

    logger.info("Application initialized successfully")


    try:
        server_config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
            loop="asyncio",
            lifespan="on",
            access_log=False,
            ssl_keyfile=_web_config.get('ssl_keyfile'),
            ssl_certfile=_web_config.get('ssl_certfile'),
        )

        _uvicorn_server = uvicorn.Server(server_config)

        # Start server non-blocking
        asyncio.create_task(_uvicorn_server.serve())

        for _ in range(20):
            if _uvicorn_server.started:
                break
            await asyncio.sleep(0.5)

        if _uvicorn_server.started:
            host_print = 'localhost' if host == "0.0.0.0" else host
            protocol = 'https' if _web_config.get('ssl_certfile') else 'http'
            logger.info(f"Starting uvicorn server on {protocol}://{host_print}:{port}")
        else:
            logger.warning('Server did not start in time')
    except Exception:
        logger.exception('failed to start server')

async def stop_server():
    global _uvicorn_server
    if _uvicorn_server is not None:
        try:
            _uvicorn_server.should_exit = True
            logger.info("Uvicorn shutdown signal sent")
        except Exception as e:
            logger.exception(f"Uvicorn shutdown error")


def verify_session(session_token: Optional[str] = Cookie(None)):
    """Dependency to verify session token."""
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    is_valid, username = _auth_manager.validate_session(session_token)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid"
        )

    return username


def check_login_rate_limit(client_ip: str) -> bool:
    """
    Check if client has exceeded login attempt rate limit.

    Args:
        client_ip: Client IP address

    Returns:
        bool: True if within limits, False if exceeded
    """
    current_time = time.time()

    with _login_lock:
        # Clean old attempts
        _login_attempts[client_ip] = [
            t for t in _login_attempts[client_ip]
            if current_time - t < LOGIN_ATTEMPT_WINDOW
        ]

        if len(_login_attempts[client_ip]) >= MAX_LOGIN_ATTEMPTS:
            return False

        _login_attempts[client_ip].append(current_time)
        return True

# ==================== Routes ====================

@app.get("/", response_class=HTMLResponse)
async def root(session_token: Optional[str] = Cookie(None)):
    """Serve dashboard or redirect to login."""
    if session_token:
        is_valid, username = _auth_manager.validate_session(session_token)
        if is_valid:
            dashboard_path = Path(__file__).parent / "templates" / "dashboard.html"
            return FileResponse(dashboard_path)

    return RedirectResponse(url="/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Serve login page."""
    login_path = Path(__file__).parent / "templates" / "login.html"
    if login_path.exists():
        with open(login_path, "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse(content="<h1>Login page not found</h1>", status_code=404)


def get_client_ip(request: Request) -> str:
    """
    Extract client IP with reverse proxy support.

    Priority:
    1. X-Real-IP (nginx/apache sets this to original client)
    2. X-Forwarded-For (first IP is original client)
    3. request.client.host (direct connection)
    """
    # Try X-Real-IP first (most reliable for reverse proxy)
    if real_ip := request.headers.get("X-Real-IP"):
        return real_ip.strip()

    # Try X-Forwarded-For (can be comma-separated list)
    if forwarded := request.headers.get("X-Forwarded-For"):
        # Take first IP (original client), strip whitespace
        return forwarded.split(",")[0].strip()

    # Fallback to direct connection
    return request.client.host if request.client else "unknown"

@app.post("/api/login")
async def login(request: LoginRequest, request2:Request, ):
    """Authenticate user and create session."""
    # Rate limiting check
    # if not check_login_rate_limit("127.0.0.1"):  # In production, use request.client.host
    real_ip = get_client_ip(request2)
    if not check_login_rate_limit(real_ip):  # In production, use request.client.host
        logger.warning(f"Login rate limit exceeded for user: {request.username} of {real_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later."
        )

    if not _auth_manager.validate_credentials(request.username, request.password):
        logger.warning(f"Failed login attempt (wrong PW) for user: {request.username} at {real_ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    session_token = _auth_manager.create_session(request.username)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="session_token",
        value=session_token,
        max_age=_auth_manager.session_timeout * 60,
        httponly=True,
        samesite="strict",
        secure=_web_config.get('use_https', False)
    )
    return response

@app.get("/api/logout")
async def logout(session_token: Optional[str] = Cookie(None)):
    """Logout user and destroy session."""
    if session_token:
        _auth_manager.destroy_session(session_token)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_token")
    return response

@app.get("/api/mqtt_status")
async def get_status(username: str = Depends(verify_session)):
    """Get current MQTT connection status."""
    try:
        return _exchange_data.get('status', {}).get('mqtt_status', False)
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get status"
        )

@app.get("/api/username")
async def get_username(username: str = Depends(verify_session)):
    """Get current authenticated username."""
    return username

@app.get("/api/live")
async def get_live_values(username: str = Depends(verify_session)):
    """Get live charger values."""
    try:
        return _exchange_data.get('status', {})
    except Exception as e:
        logger.error(f"Error getting live values: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get live values"
        )

@app.post("/api/override/set")
async def set_override(request: OverrideRequest, username: str = Depends(verify_session)):
    """Set a charging override period."""
    try:
        end_time = datetime.fromisoformat(request.end_time)
        start_time = None
        if request.start_time:
            start_time = datetime.fromisoformat(request.start_time)

        if _override_manager.set_override(end_time, start_time):
            logger.info(f"Override set by user {username}")

            return {
                "success": True,
                "message": "Override set successfully",
                "override": _override_manager.get_override_info()
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid override parameters"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid datetime format: {e}"
        )
    except Exception as e:
        logger.error(f"Error setting override: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set override"
        )

@app.get("/api/override/status")
async def get_override_status(username: str = Depends(verify_session)):
    """Get current override status."""
    return _override_manager.get_override_info()

@app.delete("/api/override")
async def clear_override( username: str = Depends(verify_session)):
    """Clear current override."""
    try:
        if _override_manager.clear_override():
            logger.info(f"Override cleared by user {username}")
            return {
                "success": True,
                "message": "Override cleared"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active override to clear"
            )
    except Exception as e:
        logger.error(f"Error clearing override: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear override"
        )

@app.post("/api/mode/set")
async def set_mode(request: ModeRequest, username: str = Depends(verify_session)):
    """Set charger mode (BASIC or ECO)."""
    if request.mode not in ["BASIC", "ECO"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mode must be 'BASIC' or 'ECO'"
        )

    try:
        publisher = _exchange_data.get('publisher')
        if not publisher:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MQTT publisher not available"
            )

        # Call publisher outside lock
        if publisher("mode", request.mode):
            logger.info(f"Mode set to {request.mode} by user {username}")
            return {
                "success": True,
                "message": f"Mode set to {request.mode}",
                "mode": request.mode
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MQTT client not connected"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting mode: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set mode"
        )

# ==================== Startup/Shutdown ====================


# ==================== Main ====================

async def main():
    def load_config(config_filename="config.yaml"):
        """
        Load YAML configuration from the config directory.

        Args:
            config_filename (str): Name of the configuration file (default: config.yaml)

        Returns:
            dict: Configuration dictionary
        """
        config_path = Path(__file__).parent.parent / "config" /  config_filename

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        return config


    configuration = load_config()
    await start_server(configuration)
    try:
        for i in range(3600):
            await asyncio.sleep(1)
            if i %10==0:
                print(i)
    finally:
        await stop_server()


if __name__ == "__main__":

    # signal.signal(signal.SIGTERM, self.exit_monitoring)
    asyncio.run(main())
