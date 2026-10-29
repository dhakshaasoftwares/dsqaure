#!/bin/sh
# Create and start a separate installation for a new client company.
#
#   scripts/new_client.sh selvam-builders 8001 [selvam.yourdomain.com]
#
# Each client gets its own folder under clients/, its own database and photo
# storage (Docker volumes named after the client), its own secret keys and
# its own port. Open http://localhost:<port> and the setup wizard asks for the
# company name and the owner's login. Point a Cloudflare Tunnel hostname at
# that port (e.g. selvam.yourdomain.com → http://localhost:8001).
set -e
cd "$(dirname "$0")/.."

NAME="$1"
PORT="$2"
if [ -z "$NAME" ] || [ -z "$PORT" ]; then
  echo "Usage: $0 <client-name> <port>      e.g. $0 selvam-builders 8001"
  exit 1
fi
case "$NAME" in
  *[!a-z0-9-]*) echo "Use only lowercase letters, numbers and '-' in the client name."; exit 1 ;;
esac

DIR="clients/$NAME"
if [ -e "$DIR/.env" ]; then
  echo "$DIR already exists. To start it again:"
  echo "  ENV_FILE=$DIR/.env docker compose -p $NAME --env-file $DIR/.env up -d"
  exit 1
fi
mkdir -p "$DIR"

random() { python3 -c "import secrets; print(secrets.token_urlsafe($1))"; }
HOST="${3:-$NAME.example.com}"

cat > "$DIR/.env" <<ENV
# Settings for client: $NAME   (created $(date +%Y-%m-%d))
SECRET_KEY=$(random 50)
DEBUG=False
ALLOWED_HOSTS=$HOST,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://$HOST,http://localhost:$PORT
TIME_ZONE=Asia/Kolkata
SECURE_COOKIES=False
WEB_PORT=$PORT
POSTGRES_DB=dsquare
POSTGRES_USER=dsquare
POSTGRES_PASSWORD=$(random 24)
CLOUDFLARE_TUNNEL_TOKEN=
ENV

ENV_FILE="$DIR/.env" docker compose -p "$NAME" --env-file "$DIR/.env" up -d --build

echo
echo "Client '$NAME' is starting on http://localhost:$PORT"
echo "Open it in a browser to run the setup wizard (company name + owner login)."
echo "Settings file: $DIR/.env   (keep it safe – it holds this client's passwords)"
echo "Edit ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS there when you give the client a web address."
