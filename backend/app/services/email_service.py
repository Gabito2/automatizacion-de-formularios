import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import BackgroundTasks
import logging

logger = logging.getLogger("EmailService")

# Configuración SMTP (por variables de entorno)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@undec.edu.ar")
USE_REAL_SMTP = SMTP_USER != "" and SMTP_PASSWORD != ""

def send_email_sync(to_email: str, subject: str, body: str):
    """Lógica síncrona para enviar correos usando smtplib."""
    logger.info(f"Preparando correo para {to_email} con asunto: '{subject}'")
    
    # Renderizado en consola (siempre visible para depuración local)
    logger.info(f"""
========================================================================
[SIMULADOR DE EMAIL INSTITUCIONAL UNdeC]
De: {SMTP_FROM}
Para: {to_email}
Asunto: {subject}
Cuerpo:
{body}
========================================================================
""")

    if not USE_REAL_SMTP:
        logger.info("SMTP no configurado (SMTP_USER/SMTP_PASSWORD vacíos). Correo enviado a la consola.")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_FROM
        msg['To'] = to_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, to_email, msg.as_string())
        server.quit()
        logger.info(f"Correo enviado exitosamente vía SMTP a {to_email}")
    except Exception as e:
        logger.error(f"Error al enviar correo vía SMTP a {to_email}: {str(e)}")

class EmailService:
    @staticmethod
    def send_account_created(background_tasks: BackgroundTasks, to_email: str, nombre: str, dni: str, temp_password: str):
        """Notificación de cuenta creada con credenciales de acceso."""
        subject = "Bienvenido a la UNdeC - Tu cuenta ha sido creada"
        body = f"""
        <html>
            <body>
                <h2>Hola {nombre}, bienvenido/a a la Universidad Nacional de Chilecito</h2>
                <p>Se ha generado tu cuenta institucional para la gestión de tu legajo digital.</p>
                <p>Tus credenciales de acceso son:</p>
                <ul>
                    <li><strong>DNI (Usuario):</strong> {dni}</li>
                    <li><strong>Contraseña:</strong> {temp_password}</li>
                </ul>
                <p><em>Nota: Tu contraseña es la misma que tu número de DNI. Te recomendamos cambiarla desde tu panel por seguridad.</em></p>
                <p>Accede al portal de matriculación para completar tu ficha personal y subir la documentación solicitada.</p>
                <br>
                <p>Saludos cordiales,<br>Secretaría de Alumnos - UNdeC</p>
            </body>
        </html>
        """
        background_tasks.add_task(send_email_sync, to_email, subject, body)

    @staticmethod
    def send_document_observed(background_tasks: BackgroundTasks, to_email: str, nombre: str, tipo_doc: str, observacion: str):
        """Notificación de documento rechazado u observado."""
        nombres_docs = {
            "dni_frente": "DNI Frente",
            "dni_dorso": "DNI Dorso",
            "foto_4x4": "Foto 4x4",
            "analitico_secundario": "Analítico Secundario",
            "partida_nacimiento": "Partida de Nacimiento",
            "formulario_inscripcion": "Formulario de Inscripción"
        }
        doc_legible = nombres_docs.get(tipo_doc, tipo_doc)
        
        subject = f"Acción requerida: Documento observado en tu legajo - UNdeC"
        body = f"""
        <html>
            <body>
                <h2>Hola {nombre},</h2>
                <p>Te informamos que durante la validación de tu legajo digital se ha observado un documento:</p>
                <p><strong>Documento:</strong> {doc_legible}</p>
                <p><strong>Observación / Motivo:</strong> "{observacion}"</p>
                <p>Por favor, ingresa al portal de preinscripción, elimina el archivo anterior y vuelve a subir un documento válido para que podamos continuar con tu matriculación.</p>
                <br>
                <p>Saludos cordiales,<br>Secretaría de Alumnos - UNdeC</p>
            </body>
        </html>
        """
        background_tasks.add_task(send_email_sync, to_email, subject, body)

    @staticmethod
    def send_general_observation(background_tasks: BackgroundTasks, to_email: str, nombre: str, observacion: str):
        """Notificación de observación general enviada por el administrador."""
        subject = "Comunicación de la UNdeC - Observación general sobre tu legajo"
        body = f"""
        <html>
            <body>
                <h2>Hola {nombre},</h2>
                <p>El equipo administrativo de la Universidad Nacional de Chilecito desea comunicarte lo siguiente:</p>
                <div style="background-color: #f8f9fa; border-left: 4px solid #3b82f6; padding: 12px 16px; margin: 16px 0; font-size: 14px;">
                    <p style="margin:0; white-space: pre-wrap;">{observacion}</p>
                </div>
                <p>Si tenés alguna consulta, no dudes en comunicarte con la secretaría de alumnos.</p>
                <br>
                <p>Saludos cordiales,<br>Secretaría de Alumnos - UNdeC</p>
            </body>
        </html>
        """
        background_tasks.add_task(send_email_sync, to_email, subject, body)

    @staticmethod
    def send_legajo_approved(background_tasks: BackgroundTasks, to_email: str, nombre: str):
        """Notificación de legajo completamente validado y aprobado."""
        subject = "Felicidades: Legajo digital aprobado - UNdeC"
        body = f"""
        <html>
            <body>
                <h2>Hola {nombre},</h2>
                <p>¡Queremos informarte que tu legajo digital ha sido validado y aprobado con éxito!</p>
                <p>Has completado el proceso de presentación documental obligatorio para tu matriculación.</p>
                <p>Próximamente nos comunicaremos contigo con más información sobre el inicio del ciclo lectivo y tu número de matrícula definitivo.</p>
                <br>
                <p>Saludos cordiales,<br>Secretaría de Alumnos - UNdeC</p>
            </body>
        </html>
        """
        background_tasks.add_task(send_email_sync, to_email, subject, body)
