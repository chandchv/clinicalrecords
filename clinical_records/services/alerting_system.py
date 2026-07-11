"""
Comprehensive alerting system with multiple notification channels.
"""

import os
import json
import logging
import smtplib
import requests
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)

class AlertingSystem:
    """
    Comprehensive alerting system with multiple notification channels.
    """
    
    def __init__(self):
        self.config = self._load_config()
        self.alert_history = []
        
    def _load_config(self):
        """Load alerting configuration."""
        return {
            'enabled': getattr(settings, 'ALERTING_ENABLED', True),
            'channels': {
                'email': {
                    'enabled': getattr(settings, 'EMAIL_ALERTS_ENABLED', True),
                    'recipients': getattr(settings, 'ALERT_EMAIL_RECIPIENTS', [
                        getattr(settings, 'ADMIN_EMAIL', 'admin@rxdoctor.com')
                    ]),
                    'smtp_host': getattr(settings, 'EMAIL_HOST', 'localhost'),
                    'smtp_port': getattr(settings, 'EMAIL_PORT', 587),
                    'smtp_user': getattr(settings, 'EMAIL_HOST_USER', ''),
                    'smtp_password': getattr(settings, 'EMAIL_HOST_PASSWORD', ''),
                    'use_tls': getattr(settings, 'EMAIL_USE_TLS', True)
                },
                'slack': {
                    'enabled': getattr(settings, 'SLACK_ALERTS_ENABLED', False),
                    'webhook_url': getattr(settings, 'SLACK_WEBHOOK_URL', ''),
                    'channel': getattr(settings, 'SLACK_ALERT_CHANNEL', '#alerts'),
                    'username': getattr(settings, 'SLACK_BOT_USERNAME', 'RxDoctor Monitor')
                },
                'webhook': {
                    'enabled': getattr(settings, 'WEBHOOK_ALERTS_ENABLED', False),
                    'url': getattr(settings, 'ALERT_WEBHOOK_URL', ''),
                    'headers': getattr(settings, 'ALERT_WEBHOOK_HEADERS', {}),
                    'timeout': getattr(settings, 'ALERT_WEBHOOK_TIMEOUT', 30)
                },
                'sms': {
                    'enabled': getattr(settings, 'SMS_ALERTS_ENABLED', False),
                    'provider': getattr(settings, 'SMS_PROVIDER', 'twilio'),
                    'account_sid': getattr(settings, 'TWILIO_ACCOUNT_SID', ''),
                    'auth_token': getattr(settings, 'TWILIO_AUTH_TOKEN', ''),
                    'from_number': getattr(settings, 'TWILIO_FROM_NUMBER', ''),
                    'to_numbers': getattr(settings, 'SMS_ALERT_NUMBERS', [])
                }
            },
            'alert_levels': {
                'info': {
                    'channels': ['email'],
                    'cooldown': 3600,  # 1 hour
                    'escalation_delay': None
                },
                'warning': {
                    'channels': ['email', 'slack'],
                    'cooldown': 1800,  # 30 minutes
                    'escalation_delay': 3600  # 1 hour
                },
                'critical': {
                    'channels': ['email', 'slack', 'sms', 'webhook'],
                    'cooldown': 300,  # 5 minutes
                    'escalation_delay': 900  # 15 minutes
                },
                'emergency': {
                    'channels': ['email', 'slack', 'sms', 'webhook'],
                    'cooldown': 60,  # 1 minute
                    'escalation_delay': 300  # 5 minutes
                }
            }
        }
    
    def send_alert(self, level, title, message, details=None, tags=None):
        """
        Send alert through configured channels based on alert level.
        """
        if not self.config['enabled']:
            logger.info(f"Alerting disabled, skipping alert: {title}")
            return False
        
        # Validate alert level
        if level not in self.config['alert_levels']:
            logger.error(f"Invalid alert level: {level}")
            return False
        
        # Check cooldown
        if not self._check_cooldown(level, title):
            logger.info(f"Alert in cooldown period: {title}")
            return False
        
        alert_config = self.config['alert_levels'][level]
        channels = alert_config['channels']
        
        # Create alert record
        alert_record = {
            'timestamp': datetime.now(),
            'level': level,
            'title': title,
            'message': message,
            'details': details,
            'tags': tags or [],
            'channels_sent': [],
            'channels_failed': []
        }
        
        # Send through each configured channel
        success_count = 0
        for channel in channels:
            try:
                if self._send_to_channel(channel, level, title, message, details, tags):
                    alert_record['channels_sent'].append(channel)
                    success_count += 1
                else:
                    alert_record['channels_failed'].append(channel)
            except Exception as e:
                logger.error(f"Error sending alert to {channel}: {str(e)}")
                alert_record['channels_failed'].append(channel)
        
        # Record alert in history
        self.alert_history.append(alert_record)
        
        # Keep only last 1000 alerts
        if len(self.alert_history) > 1000:
            self.alert_history = self.alert_history[-1000:]
        
        # Log alert
        logger.info(f"Alert sent: {level} - {title} (Success: {success_count}/{len(channels)})")
        
        return success_count > 0
    
    def _check_cooldown(self, level, title):
        """Check if alert is in cooldown period."""
        cooldown_seconds = self.config['alert_levels'][level]['cooldown']
        
        # Find last alert with same level and title
        for alert in reversed(self.alert_history):
            if alert['level'] == level and alert['title'] == title:
                time_since = (datetime.now() - alert['timestamp']).total_seconds()
                return time_since >= cooldown_seconds
        
        # No previous alert found, can send
        return True
    
    def _send_to_channel(self, channel, level, title, message, details, tags):
        """Send alert to specific channel."""
        channel_config = self.config['channels'].get(channel, {})
        
        if not channel_config.get('enabled', False):
            logger.info(f"Channel {channel} is disabled")
            return False
        
        if channel == 'email':
            return self._send_email_alert(level, title, message, details, tags)
        elif channel == 'slack':
            return self._send_slack_alert(level, title, message, details, tags)
        elif channel == 'webhook':
            return self._send_webhook_alert(level, title, message, details, tags)
        elif channel == 'sms':
            return self._send_sms_alert(level, title, message, details, tags)
        else:
            logger.error(f"Unknown alert channel: {channel}")
            return False
    
    def _send_email_alert(self, level, title, message, details, tags):
        """Send email alert."""
        try:
            config = self.config['channels']['email']
            
            # Create email content
            subject = f"[{level.upper()}] RxDoctor Alert: {title}"
            
            # Use template if available
            try:
                email_body = render_to_string('clinical_records/alert_email.html', {
                    'level': level,
                    'title': title,
                    'message': message,
                    'details': details,
                    'tags': tags,
                    'timestamp': datetime.now(),
                    'server_name': os.uname().nodename if hasattr(os, 'uname') else 'Unknown'
                })
            except:
                # Fallback to plain text
                email_body = f"""
RxDoctor Alert

Level: {level.upper()}
Title: {title}
Message: {message}

Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Server: {os.uname().nodename if hasattr(os, 'uname') else 'Unknown'}

{f'Details: {details}' if details else ''}
{f'Tags: {", ".join(tags)}' if tags else ''}

This is an automated alert from the RxDoctor monitoring system.
                """
            
            # Send email
            send_mail(
                subject,
                email_body,
                settings.DEFAULT_FROM_EMAIL,
                config['recipients'],
                fail_silently=False,
                html_message=email_body if '<html>' in email_body else None
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending email alert: {str(e)}")
            return False
    
    def _send_slack_alert(self, level, title, message, details, tags):
        """Send Slack alert."""
        try:
            config = self.config['channels']['slack']
            
            if not config['webhook_url']:
                logger.error("Slack webhook URL not configured")
                return False
            
            # Determine color based on level
            color_map = {
                'info': '#36a64f',      # Green
                'warning': '#ff9500',   # Orange
                'critical': '#ff0000',  # Red
                'emergency': '#8b0000'  # Dark Red
            }
            
            color = color_map.get(level, '#36a64f')
            
            # Create Slack message
            slack_message = {
                'channel': config['channel'],
                'username': config['username'],
                'icon_emoji': ':warning:' if level in ['warning', 'critical', 'emergency'] else ':information_source:',
                'attachments': [
                    {
                        'color': color,
                        'title': f"{level.upper()}: {title}",
                        'text': message,
                        'fields': [
                            {
                                'title': 'Server',
                                'value': os.uname().nodename if hasattr(os, 'uname') else 'Unknown',
                                'short': True
                            },
                            {
                                'title': 'Timestamp',
                                'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'short': True
                            }
                        ],
                        'footer': 'RxDoctor Monitoring',
                        'ts': int(datetime.now().timestamp())
                    }
                ]
            }
            
            # Add details if provided
            if details:
                slack_message['attachments'][0]['fields'].append({
                    'title': 'Details',
                    'value': details[:1000] + '...' if len(details) > 1000 else details,
                    'short': False
                })
            
            # Add tags if provided
            if tags:
                slack_message['attachments'][0]['fields'].append({
                    'title': 'Tags',
                    'value': ', '.join(tags),
                    'short': True
                })
            
            # Send to Slack
            response = requests.post(
                config['webhook_url'],
                json=slack_message,
                timeout=30
            )
            
            response.raise_for_status()
            return True
            
        except Exception as e:
            logger.error(f"Error sending Slack alert: {str(e)}")
            return False
    
    def _send_webhook_alert(self, level, title, message, details, tags):
        """Send webhook alert."""
        try:
            config = self.config['channels']['webhook']
            
            if not config['url']:
                logger.error("Webhook URL not configured")
                return False
            
            # Create webhook payload
            payload = {
                'level': level,
                'title': title,
                'message': message,
                'details': details,
                'tags': tags,
                'timestamp': datetime.now().isoformat(),
                'server': os.uname().nodename if hasattr(os, 'uname') else 'Unknown',
                'source': 'rxdoctor-monitoring'
            }
            
            # Send webhook
            headers = {
                'Content-Type': 'application/json',
                **config.get('headers', {})
            }
            
            response = requests.post(
                config['url'],
                json=payload,
                headers=headers,
                timeout=config.get('timeout', 30)
            )
            
            response.raise_for_status()
            return True
            
        except Exception as e:
            logger.error(f"Error sending webhook alert: {str(e)}")
            return False
    
    def _send_sms_alert(self, level, title, message, details, tags):
        """Send SMS alert."""
        try:
            config = self.config['channels']['sms']
            
            if config['provider'] == 'twilio':
                return self._send_twilio_sms(level, title, message, config)
            else:
                logger.error(f"Unsupported SMS provider: {config['provider']}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending SMS alert: {str(e)}")
            return False
    
    def _send_twilio_sms(self, level, title, message, config):
        """Send SMS via Twilio."""
        try:
            from twilio.rest import Client
            
            if not all([config['account_sid'], config['auth_token'], config['from_number']]):
                logger.error("Twilio configuration incomplete")
                return False
            
            client = Client(config['account_sid'], config['auth_token'])
            
            # Create SMS message
            sms_message = f"[{level.upper()}] RxDoctor Alert: {title}\n\n{message}"
            
            # Truncate if too long
            if len(sms_message) > 160:
                sms_message = sms_message[:157] + '...'
            
            # Send to all configured numbers
            success_count = 0
            for to_number in config['to_numbers']:
                try:
                    client.messages.create(
                        body=sms_message,
                        from_=config['from_number'],
                        to=to_number
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"Error sending SMS to {to_number}: {str(e)}")
            
            return success_count > 0
            
        except ImportError:
            logger.error("Twilio library not installed")
            return False
        except Exception as e:
            logger.error(f"Error sending Twilio SMS: {str(e)}")
            return False
    
    def get_alert_history(self, limit=100, level=None, since=None):
        """Get alert history with optional filtering."""
        alerts = self.alert_history
        
        # Filter by level
        if level:
            alerts = [a for a in alerts if a['level'] == level]
        
        # Filter by time
        if since:
            alerts = [a for a in alerts if a['timestamp'] >= since]
        
        # Sort by timestamp (newest first)
        alerts = sorted(alerts, key=lambda x: x['timestamp'], reverse=True)
        
        # Limit results
        return alerts[:limit]
    
    def get_alert_statistics(self, since=None):
        """Get alert statistics."""
        if since is None:
            since = datetime.now() - timedelta(days=7)  # Last 7 days
        
        recent_alerts = [a for a in self.alert_history if a['timestamp'] >= since]
        
        stats = {
            'total_alerts': len(recent_alerts),
            'by_level': {},
            'by_channel': {},
            'success_rate': 0,
            'most_common_titles': {}
        }
        
        # Count by level
        for alert in recent_alerts:
            level = alert['level']
            stats['by_level'][level] = stats['by_level'].get(level, 0) + 1
        
        # Count by channel
        for alert in recent_alerts:
            for channel in alert['channels_sent']:
                stats['by_channel'][channel] = stats['by_channel'].get(channel, 0) + 1
        
        # Calculate success rate
        total_attempts = sum(len(a['channels_sent']) + len(a['channels_failed']) for a in recent_alerts)
        successful_attempts = sum(len(a['channels_sent']) for a in recent_alerts)
        
        if total_attempts > 0:
            stats['success_rate'] = (successful_attempts / total_attempts) * 100
        
        # Most common alert titles
        title_counts = {}
        for alert in recent_alerts:
            title = alert['title']
            title_counts[title] = title_counts.get(title, 0) + 1
        
        stats['most_common_titles'] = dict(sorted(title_counts.items(), key=lambda x: x[1], reverse=True)[:10])
        
        return stats
    
    def test_channels(self):
        """Test all configured alert channels."""
        results = {}
        
        for channel_name, channel_config in self.config['channels'].items():
            if not channel_config.get('enabled', False):
                results[channel_name] = {'status': 'disabled', 'message': 'Channel is disabled'}
                continue
            
            try:
                success = self._send_to_channel(
                    channel_name,
                    'info',
                    'Test Alert',
                    'This is a test alert to verify channel configuration.',
                    'Channel test details',
                    ['test', 'configuration']
                )
                
                results[channel_name] = {
                    'status': 'success' if success else 'failed',
                    'message': 'Test alert sent successfully' if success else 'Failed to send test alert'
                }
                
            except Exception as e:
                results[channel_name] = {
                    'status': 'error',
                    'message': str(e)
                }
        
        return results