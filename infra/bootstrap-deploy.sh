#!/bin/bash
# FULL-AUTO bootstrap for @FileFromLinkBot on a fresh Ubuntu 24.04 EC2 instance.
# Use as EC2 "User data" (paste at launch) OR run manually:  sudo bash bootstrap-deploy.sh
# It installs Docker, clones the repo, writes .env (random API_SECRET),
# and starts the stack. ONLY remaining step: set BOT_TOKEN (see ffl-set-token below).
set -eux
exec > >(tee -a /var/log/file-from-link-bootstrap.log) 2>&1
apt-get update -y
apt-get install -y ca-certificates curl git openssl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable --now docker
usermod -aG docker ubuntu || true
[ -d /opt/file-from-link ] || git clone https://github.com/rzashakeri/file-from-link.git /opt/file-from-link
cd /opt/file-from-link
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s|^API_SECRET=.*|API_SECRET=$(openssl rand -hex 32)|" .env
fi
docker compose up -d --build || true
cat > /usr/local/bin/ffl-set-token << 'EOS'
#!/bin/bash
# Usage: sudo ffl-set-token 123456:ABC...   (token from BotFather)
set -eu
sed -i "s|^BOT_TOKEN=.*|BOT_TOKEN=$1|" /opt/file-from-link/.env
cd /opt/file-from-link && docker compose up -d
docker compose ps
EOS
chmod +x /usr/local/bin/ffl-set-token
echo "BOOTSTRAP DONE. Now run:  sudo ffl-set-token <BOT_TOKEN>"
