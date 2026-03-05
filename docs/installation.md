# Installation Guide

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Python | 3.10+ | 3.12 |
| Node.js | 18+ | 20 LTS |
| MariaDB | 10.6+ | 10.11 |
| Redis | 6+ | 7 |
| RAM | 2 GB | 4 GB |
| Disk | 10 GB | 20 GB |

## Step 1: Install System Dependencies

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install -y python3-dev python3-pip python3-venv \
    nodejs npm redis-server mariadb-server mariadb-client \
    git curl wkhtmltopdf
```

### Configure MariaDB

```bash
sudo mysql_secure_installation

# Create database user
sudo mysql -e "CREATE USER 'frappe'@'localhost' IDENTIFIED BY 'your_password';"
sudo mysql -e "GRANT ALL PRIVILEGES ON *.* TO 'frappe'@'localhost';"
sudo mysql -e "FLUSH PRIVILEGES;"
```

Add to `/etc/mysql/mariadb.conf.d/50-server.cnf` under `[mysqld]`:

```ini
character-set-client-handshake = FALSE
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
```

Restart: `sudo systemctl restart mariadb`

## Step 2: Install Frappe Bench

```bash
pip install frappe-bench
bench init frappe-bench --frappe-branch version-15
cd frappe-bench
```

## Step 3: Create Site

```bash
bench new-site nixfact.local --mariadb-root-password your_root_password
```

## Step 4: Install ERPNext

```bash
bench get-app erpnext --branch version-15
bench --site nixfact.local install-app erpnext
```

## Step 5: Install NIXFact

```bash
bench get-app https://github.com/NickAldewereld/erpnext-nixauce
bench --site nixfact.local install-app nixfact_integration
```

## Step 6: Start

```bash
bench start
```

Visit http://nixfact.local:8000 and log in with Administrator credentials.

## Step 7: Configure

1. Go to **NixFact Instellingen** (search in the desk)
2. Set your invoice prefix, payment terms, BTW rates
3. (Optional) Configure Ponto bank connection
4. (Optional) Configure Mollie payments
5. Enable the scheduler: `bench enable-scheduler`

## Production Deployment

```bash
# Set up for production
sudo bench setup production your_user

# Enable SSL with Let's Encrypt
sudo bench setup lets-encrypt nixfact.yourdomain.com
```

## Updating

```bash
cd frappe-bench
bench update
bench --site nixfact.local migrate
bench restart
```

## Troubleshooting

### Scheduler not running
```bash
bench enable-scheduler
bench doctor
```

### Migration errors
```bash
bench --site nixfact.local migrate --rebuild-website
bench --site nixfact.local clear-cache
```

### Permission errors
```bash
bench --site nixfact.local set-admin-password new_password
```
