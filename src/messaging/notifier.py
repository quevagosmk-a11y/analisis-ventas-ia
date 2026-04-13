from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Dict, Iterable, List

try:
    from twilio.rest import Client as TwilioClient
except ImportError:  # pragma: no cover - optional dependency
    TwilioClient = None  # type: ignore[assignment]


class Notifier:
    """Notificador con soporte para consola, correo y canales Twilio."""

    def __init__(self, service: str | None = None):
        self.service = (
            service or os.environ.get("NOTIFIER_SERVICE", "console")
        ).lower()
        # SMTP settings
        self.email_from = os.environ.get("NOTIFIER_EMAIL_FROM")
        self.email_to = [
            addr.strip()
            for addr in os.environ.get("NOTIFIER_EMAIL_TO", "").split(",")
            if addr.strip()
        ]
        self.smtp_host = os.environ.get("SMTP_HOST")
        self.smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        self.smtp_username = os.environ.get("SMTP_USERNAME")
        self.smtp_password = os.environ.get("SMTP_PASSWORD")
        # Twilio settings
        self.twilio_account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        self.twilio_auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        self.twilio_messaging_service_sid = os.environ.get(
            "TWILIO_MESSAGING_SERVICE_SID"
        )
        self.twilio_sms_from = os.environ.get("TWILIO_SMS_FROM")
        self.twilio_whatsapp_from = os.environ.get("TWILIO_WHATSAPP_FROM")
        self.twilio_sms_to = [
            addr.strip()
            for addr in os.environ.get("NOTIFIER_SMS_TO", "").split(",")
            if addr.strip()
        ]
        self.twilio_whatsapp_to = [
            addr.strip()
            for addr in os.environ.get("NOTIFIER_WHATSAPP_TO", "").split(",")
            if addr.strip()
        ]

    # ------------------------------------------------------------------
    # Metodos internos
    # ------------------------------------------------------------------

    def _can_send_email(self) -> bool:
        return all(
            [
                self.email_from,
                self.email_to,
                self.smtp_host,
                self.smtp_username,
                self.smtp_password,
            ]
        )

    def _send_email(self, subject: str, body: str) -> None:
        if not self._can_send_email():
            print("[notifier] Configuracion SMTP incompleta, usando modo consola.")
            self._emit_console(subject + "\n" + body)
            return
        message = EmailMessage()
        message["From"] = self.email_from
        message["To"] = ", ".join(self.email_to)
        message["Subject"] = subject
        message.set_content(body)
        context = ssl.create_default_context()
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(message)
        except Exception as exc:
            print(f"[notifier] Error enviando correo: {exc}. Se imprime en consola.")
            self._emit_console(subject + "\n" + body)

    def _twilio_client(self):
        if not all([self.twilio_account_sid, self.twilio_auth_token]):
            return None
        if TwilioClient is None:
            return None
        try:
            return TwilioClient(self.twilio_account_sid, self.twilio_auth_token)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[notifier] No se pudo inicializar Twilio: {exc}")
            return None

    def _send_twilio_message(self, subject: str, body: str) -> None:
        client = self._twilio_client()
        if client is None:
            print("[notifier] Configuracion Twilio incompleta, usando modo consola.")
            self._emit_console(f"{subject}\n{body}")
            return
        text = f"{subject}\n{body}".strip()
        try:
            if self.service == "twilio_sms":
                from_number = self.twilio_sms_from
                recipients = self.twilio_sms_to
                channel_prefix = ""
            else:  # whatsapp
                from_number = self.twilio_whatsapp_from
                recipients = self.twilio_whatsapp_to
                channel_prefix = "whatsapp:"
            if not from_number or not recipients:
                raise ValueError("Faltan remitente o destinatarios Twilio")
            for to_addr in recipients:
                target = (
                    to_addr
                    if channel_prefix == ""
                    else f"whatsapp:{to_addr.replace('whatsapp:', '')}"
                )
                client.messages.create(
                    body=text,
                    from_=channel_prefix + from_number.replace("whatsapp:", ""),
                    to=target,
                )
        except Exception as exc:
            print(
                f"[notifier] Error enviando via Twilio: {exc}. Se imprime en consola."
            )
            self._emit_console(f"{subject}\n{body}")

    def _emit_console(self, msg: str) -> None:
        print(msg)

    def _emit(self, subject: str, lines: Iterable[str]) -> None:
        payload = "\n".join(lines)
        if self.service == "email":
            self._send_email(subject, payload)
        elif self.service in {"twilio_sms", "twilio_whatsapp"}:
            self._send_twilio_message(subject, payload)
        else:
            self._emit_console(f"{subject}\n{payload}")

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def send_top_product_notification(self, top_product: Dict[str, Any]) -> None:
        if not top_product:
            return
        self._emit(
            "Top producto",
            [
                f"Producto: {top_product.get('product')}",
                f"Unidades: {top_product.get('qty')}",
                f"Ingresos: {top_product.get('revenue', '-')}",
            ],
        )

    def send_offer_suggestions(self, suggestions: List[str]) -> None:
        if not suggestions:
            return
        lines = [f"- {s}" for s in suggestions]
        self._emit("Sugerencias de ofertas", lines)

    def send_combo_suggestions(self, combos: List[Dict[str, Any]]) -> None:
        if not combos:
            return
        lines = []
        for combo in combos:
            items = combo.get("items") or combo.get("products") or []
            names = " + ".join(items) if isinstance(items, list) else str(items)
            support = combo.get("support_pct")
            ticket = combo.get("avg_ticket")
            detail = names
            if isinstance(support, (int, float)):
                detail += f" ({support:.1f}% pedidos)"
            if ticket:
                detail += f" | ticket {ticket}"
            lines.append(f"- {detail}")
        self._emit("Combos frecuentes", lines)

    def send_restock_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        if not alerts:
            return
        lines = []
        for alert in alerts:
            name = alert.get("product") or alert.get("nombre")
            stock = alert.get("stock")
            minimum = alert.get("min_stock")
            recommended = alert.get("recommended") or alert.get("recomendar_comprar")
            target = alert.get("target_stock")
            detail = f"- {name}: stock {stock} / minimo {minimum}"
            if recommended:
                detail += f", pedir {recommended}"
            if target:
                detail += f" (objetivo {target})"
            lines.append(detail)
        self._emit("Reposicion prioritaria", lines)
