import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def mail_to_log(message_string: str, subject: str):
    """Dummy function that writes to log instead of Sending Mail if no Mail config is present.

    :param message_string:
    :param subject:
    :return:
    """
    logger.info(f"{subject}:\t{message_string}")


class Mailer:
    def __init__(self, configuration):
        self.mail_settings = configuration

    def send_mail(self, Message: str, Subject: str):
        """Sends a mail all is defined at yaml configuration.

        :param Message: Message body in plain text only
        :param Subject: Subject of message
        :return:
        """
        # Create a secure SSL context
        ssl_context = ssl.create_default_context()

        # Create a multipart message and set headers
        message = MIMEMultipart()
        message["From"] = self.mail_settings["From"]
        message["To"] = self.mail_settings["To"]
        message["Subject"] = Subject

        # Add body to email
        message.attach(MIMEText(Message, "plain"))

        # Add attachment to message and convert message to string

        with smtplib.SMTP_SSL(
            self.mail_settings["Server"],
            self.mail_settings["port"],
            context=ssl_context,
        ) as server:
            server.login(self.mail_settings["From"], self.mail_settings["Password"])
            # errors = server.sendmail(self.mail_settings['From'], self.mail_settings['To'], message.as_string())
            errors = server.send_message(message)
        if len(errors) == 0:
            logger.info("Mail sent - %s:\t%s", Subject, Message)
        else:
            logger.error("Sending message %s - %s:\t%s", str(errors), Subject, Message)
