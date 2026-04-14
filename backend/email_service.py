"""
Email Delivery Service

Sends HTML digest emails for scheduled agent runs.
Configure via env vars:
  SMTP_HOST     — SMTP server host (default: smtp.gmail.com)
  SMTP_PORT     — SMTP port (default: 587)
  SMTP_USER     — Sender email address
  SMTP_PASSWORD — Sender email password / app password
  EMAIL_FROM    — From display name + address (default: SMTP_USER)
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

ALERT_COLORS = {
    "high":   "#EF4444",
    "medium": "#F59E0B",
    "low":    "#10B981",
    "none":   "#6B7280",
}

ALERT_LABELS = {
    "high":   "HIGH ALERT",
    "medium": "NEW FINDINGS",
    "low":    "ROUTINE UPDATE",
    "none":   "NO CHANGES",
}


def send_run_email(to_address: str, agent_name: str, outcome: dict) -> None:
    """
    Send an HTML email summarising an agent run.

    Args:
        to_address:  Recipient email
        agent_name:  Name of the scheduled agent
        outcome:     Result dict from AgentRunnerService.execute()
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")

    if not smtp_user or not smtp_password:
        logger.warning("SMTP credentials not configured — skipping email delivery")
        return

    alert_level = outcome.get("alert_level", "none")
    material_change = outcome.get("material_change", False)
    summary = outcome.get("findings_summary", "")
    key_findings = outcome.get("key_findings", [])
    tickers = outcome.get("tickers_analyzed", [])

    subject = _build_subject(agent_name, alert_level, material_change)
    html_body = _build_html(agent_name, alert_level, summary, key_findings, tickers, outcome)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = os.getenv("EMAIL_FROM", smtp_user)
    msg["To"] = to_address
    msg.attach(MIMEText(_build_plain(agent_name, summary, key_findings), "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_address, msg.as_string())
        logger.info(f"Email sent to {to_address} for agent '{agent_name}'")
    except Exception as exc:
        logger.error(f"Failed to send email to {to_address}: {exc}")
        raise


def _build_subject(agent_name: str, alert_level: str, material_change: bool) -> str:
    label = ALERT_LABELS.get(alert_level, "UPDATE")
    flag = " ⚡" if alert_level == "high" else ""
    return f"[{label}] {agent_name}{flag} — Phronesis AI"


def _build_plain(agent_name: str, summary: str, key_findings: list) -> str:
    findings_text = "\n".join(f"  • {f}" for f in key_findings)
    return f"""{agent_name} — Research Update

{summary}

Key Findings:
{findings_text}

---
Powered by Phronesis AI
"""


def _build_html(
    agent_name: str,
    alert_level: str,
    summary: str,
    key_findings: list,
    tickers: list,
    outcome: dict,
) -> str:
    accent = ALERT_COLORS.get(alert_level, "#6B7280")
    alert_label = ALERT_LABELS.get(alert_level, "UPDATE")
    tickers_str = " · ".join(tickers) if tickers else ""
    findings_html = "".join(
        f'<li style="margin-bottom:8px;color:#374151;">{f}</li>'
        for f in key_findings
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{agent_name}</title>
</head>
<body style="margin:0;padding:0;background:#F9FAFB;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#F9FAFB;padding:40px 20px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background:#FFFFFF;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">

          <!-- Header -->
          <tr>
            <td style="background:#0F172A;padding:32px 40px;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <span style="color:#FFFFFF;font-size:20px;font-weight:700;letter-spacing:-0.02em;">Phronesis AI</span>
                    <br>
                    <span style="color:#94A3B8;font-size:13px;">Financial Intelligence</span>
                  </td>
                  <td align="right">
                    <span style="background:{accent};color:#FFFFFF;font-size:11px;font-weight:700;padding:4px 10px;border-radius:20px;letter-spacing:0.05em;">{alert_label}</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Agent name + tickers -->
          <tr>
            <td style="padding:32px 40px 0;">
              <p style="margin:0;font-size:22px;font-weight:700;color:#0F172A;letter-spacing:-0.02em;">{agent_name}</p>
              {f'<p style="margin:8px 0 0;font-size:13px;color:#6B7280;font-weight:500;">{tickers_str}</p>' if tickers_str else ''}
            </td>
          </tr>

          <!-- Summary -->
          <tr>
            <td style="padding:24px 40px 0;">
              <p style="margin:0;font-size:15px;line-height:1.6;color:#374151;">{summary}</p>
            </td>
          </tr>

          <!-- Key Findings -->
          {f'''<tr>
            <td style="padding:24px 40px 0;">
              <p style="margin:0 0 12px;font-size:12px;font-weight:700;color:#6B7280;text-transform:uppercase;letter-spacing:0.06em;">Key Findings</p>
              <ul style="margin:0;padding-left:20px;">
                {findings_html}
              </ul>
            </td>
          </tr>''' if key_findings else ''}

          <!-- Divider -->
          <tr>
            <td style="padding:32px 40px 0;">
              <hr style="border:none;border-top:1px solid #E5E7EB;">
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:24px 40px 32px;">
              <p style="margin:0;font-size:12px;color:#9CA3AF;">
                This report was generated automatically by your <strong>{agent_name}</strong> agent.
                <br>Powered by Phronesis AI · Financial Intelligence Platform
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
