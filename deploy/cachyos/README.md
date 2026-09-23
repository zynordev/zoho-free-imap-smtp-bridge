# CachyOS / Arch Linux Yerel Kurulum Kilavuzu

Bu dizin, Zoho Mail Bridge sistemini CachyOS veya Arch Linux uzerinde yerel olarak (localhost) calistirmak icin hazirlanmistir.

## Avantajlari
- VDS veya dis sunucu gerektirmez.
- Let's Encrypt veya dis domain DNS ayari gerektirmez (localhost SSL sertifikasi otomatik uretilir).
- Dovecot ve Postfix yalnizca `127.0.0.1` uzerinde dinler, dis aglara tamamen kapalidir.

## Kurulum

1. Yapilandirma dosyalarini hazirlayin:
   ```bash
   cp conf/mailbridge.env.example conf/mailbridge.env
   cp conf/users.example conf/users
   ```
   `conf/mailbridge.env` icerisine Zoho OAuth token bilgilerinizi girin.
   `conf/users` icerisine Dovecot kullanici hesaplarinizi girin.

2. Kurulum scriptini root olarak calistirin:
   ```bash
   sudo ./kur-cachyos.sh
   ```

Script otomatik olarak paketleri kurar, kullanicilari olusturur, SSL sertifikasini uretir ve `dovecot`, `postfix`, `mailbridge` servislerini baslatir.

## Thunderbird Yapilandirmasi

- **Gelen Sunucu (IMAP):**
  - Sunucu: `127.0.0.1`
  - Port: `993`
  - Baglanti Guvenligi: `SSL/TLS`
  - Kimlik Dogrulama: `Normal Parola`
  - Kullanici Adi: `kullanici@domain.com`

- **Giden Sunucu (SMTP):**
  - Sunucu: `127.0.0.1`
  - Port: `587`
  - Baglanti Guvenligi: `STARTTLS`
  - Kimlik Dogrulama: `Normal Parola`
  - Kullanici Adi: `kullanici@domain.com`
