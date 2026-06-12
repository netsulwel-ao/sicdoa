"""
Management command para backup automático da base de dados.

Uso:
    python manage.py backup_db

Agendamento (APScheduler em governanca/scheduler.py):
    - Diário às 3:00 da manhã

Comportamento:
    1. Executa mysqldump com --single-transaction, --routines, --triggers
    2. Comprime com gzip
    3. Guarda no diretório BACKUP_DIR (configurável)
    4. Remove backups mais antigos que BACKUP_RETENTION_DAYS
    5. Envia o ficheiro por email se ≤ 20MB, senão envia notificação
"""
import gzip
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Cria backup da base de dados MySQL, comprime e envia por email'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-email',
            action='store_true',
            help='Não enviar email com o backup',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Iniciando backup da base de dados...'))

        # Configurações
        backup_dir = Path(getattr(settings, 'BACKUP_DIR', os.path.join(settings.BASE_DIR, 'backups')))
        retention_days = getattr(settings, 'BACKUP_RETENTION_DAYS', 30)
        backup_email_to = getattr(settings, 'BACKUP_EMAIL_TO', '')
        db_settings = settings.DATABASES.get('default', {})

        # Garantir que o diretório de backup existe
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Nome do ficheiro
        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        backup_name = f'backup_sicdoa_{timestamp}.sql'
        backup_path = backup_dir / backup_name

        # Credenciais da BD
        db_name = db_settings.get('NAME', '')
        db_user = db_settings.get('USER', 'root')
        db_password = db_settings.get('PASSWORD', '')
        db_host = db_settings.get('HOST', '127.0.0.1')
        db_port = db_settings.get('PORT', '3306')

        if not db_name:
            self.stdout.write(self.style.ERROR('Nome da base de dados não configurado.'))
            return

        # 1. Executar mysqldump
        self.stdout.write(f'A conectar a {db_host}:{db_port}/{db_name}...')
        try:
            env = os.environ.copy()
            if db_password:
                env['MYSQL_PWD'] = db_password

            result = subprocess.run(
                [
                    'mysqldump',
                    f'--host={db_host}',
                    f'--port={db_port}',
                    f'--user={db_user}',
                    '--single-transaction',
                    '--routines',
                    '--triggers',
                    '--add-drop-database',
                    '--databases',
                    db_name,
                ],
                capture_output=True,
                text=True,
                env=env,
                timeout=300,
            )

            if result.returncode != 0:
                self.stdout.write(self.style.ERROR(f'mysqldump falhou:\n{result.stderr}'))
                return

            sql_content = result.stdout
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(
                'mysqldump não encontrado. Verifique se o MySQL Client está instalado '
                'e no PATH do sistema.'
            ))
            return
        except subprocess.TimeoutExpired:
            self.stdout.write(self.style.ERROR('mysqldump excedeu o tempo limite (5 minutos).'))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Erro ao executar mysqldump: {e}'))
            return

        # 2. Comprimir com gzip
        gz_path = backup_path.with_suffix('.sql.gz')
        self.stdout.write('A comprimir...')
        try:
            with open(backup_path, 'wb') as f_raw:
                f_raw.write(sql_content.encode('utf-8'))
            with open(backup_path, 'rb') as f_in:
                with gzip.open(gz_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            # Remover ficheiro não comprimido
            backup_path.unlink()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Erro ao comprimir: {e}'))
            return

        tamanho_mb = gz_path.stat().st_size / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(
            f'Backup criado: {gz_path.name} ({tamanho_mb:.2f} MB)'
        ))

        # 3. Remover backups antigos
        self._limpar_backups_antigos(backup_dir, retention_days)

        # 4. Enviar por email (se configurado e --no-email não estiver activo)
        if backup_email_to and not options.get('no_email'):
            self._enviar_email(backup_email_to, gz_path, tamanho_mb, db_name)

        self.stdout.write(self.style.SUCCESS('Backup concluído com sucesso!'))

    def _limpar_backups_antigos(self, backup_dir, retention_days):
        """Remove backups mais antigos que retention_days."""
        if retention_days <= 0:
            return
        limite = timezone.now() - timedelta(days=retention_days)
        removidos = 0
        for f in backup_dir.glob('backup_sicdoa_*.sql.gz'):
            try:
                data_str = f.stem.replace('backup_sicdoa_', '')[:19]
                data_file = datetime.strptime(data_str, '%Y-%m-%d_%H%M%S')
                data_file = timezone.make_aware(data_file)
                if data_file < limite:
                    f.unlink()
                    removidos += 1
            except (ValueError, IndexError):
                continue
        if removidos:
            self.stdout.write(f'Removidos {removidos} backup(s) antigo(s).')

    def _enviar_email(self, to_email, gz_path, tamanho_mb, db_name):
        """Envia o backup por email."""
        assunto = f'Backup SICDOA — {timezone.now():%d/%m/%Y}'
        MAX_ATTACHMENT_MB = 20

        try:
            email = EmailMessage(
                subject=assunto,
                body=self._corpo_email(gz_path, tamanho_mb, db_name),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[to_email],
            )

            if tamanho_mb <= MAX_ATTACHMENT_MB:
                with open(gz_path, 'rb') as f:
                    email.attach(gz_path.name, f.read(), 'application/gzip')
            else:
                email.body += (
                    f'\n\nNOTA: O ficheiro de backup ({tamanho_mb:.2f} MB) excede o '
                    f'limite de {MAX_ATTACHMENT_MB} MB para anexos por email.\n'
                    f'O backup está disponível localmente em: {gz_path}'
                )

            email.send()
            self.stdout.write(self.style.SUCCESS(f'Email enviado para {to_email}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Erro ao enviar email: {e}'))

    @staticmethod
    def _corpo_email(gz_path, tamanho_mb, db_name):
        return (
            f'Backup da base de dados {db_name} realizado com sucesso.\n\n'
            f'Detalhes:\n'
            f'  Ficheiro: {gz_path.name}\n'
            f'  Tamanho: {tamanho_mb:.2f} MB\n'
            f'  Data: {datetime.now():%d/%m/%Y %H:%M:%S}\n'
            f'  Base de Dados: {db_name}\n\n'
            f'---\n'
            f'SICDOA — Sistema Integrado de Gestão Aduaneira\n'
            f'Backup automático diário'
        )
