#!/bin/bash
# Despliegue de la API publica (hc-fastapi).
#
# Ejecutar en el VPS como root:
#   cd /opt/hardcoregames/repos/fastapi && git checkout main && git pull --ff-only
#   bash deploy/deploy-fastapi.sh
#
# IMPORTANTE: el SQL del radar tiene que estar aplicado ANTES, porque esta
# version del modelo ya espera las columnas sobre_pedido y radar_tienda. Ese
# SQL lo aplica el despliegue del backend de Django
# (deploy/deploy-radar-fase0.sh en hardcoregames-back).
set -e
cd /root

REPO=/opt/hardcoregames/repos/fastapi
TAG=candidate-main

echo "== 1/4 Estado del checkout"
git -C "$REPO" fetch -q origin
RAMA=$(git -C "$REPO" branch --show-current)
echo "   rama:   $RAMA"
echo "   commit: $(git -C "$REPO" log --oneline -1)"
if [ "$RAMA" != "main" ]; then
  echo "ERROR: el checkout esta en '$RAMA', no en main. Se construiria codigo equivocado."
  echo "       git -C $REPO checkout main && git -C $REPO pull --ff-only"
  exit 1
fi
if [ "$(git -C "$REPO" rev-parse HEAD)" != "$(git -C "$REPO" rev-parse origin/main)" ]; then
  echo "ERROR: el checkout no esta al dia con origin/main. Corre: git -C $REPO pull --ff-only"
  exit 1
fi

echo "== 2/4 Comprobando que las columnas nuevas existan en la base"
COLS=$(docker exec hc-postgres psql -U hardcoregames -d hardcoregames -tAc \
  "select count(*) from information_schema.columns where table_name='products_products' and column_name in ('sobre_pedido','radar_tienda')" | tr -d ' ')
if [ "$COLS" != "2" ]; then
  echo "ERROR: faltan columnas en products_products (encontradas: $COLS de 2)."
  echo "       Aplica primero el SQL del radar desde el repo de Django:"
  echo "       bash /opt/hardcoregames/repos/django/deploy/deploy-radar-fase0.sh"
  exit 1
fi
echo "   columnas OK"

echo "== 3/4 Construyendo y probando hc-fastapi:$TAG"
docker build -t "hc-fastapi:$TAG" "$REPO"
docker rm -f hc-fastapi-test >/dev/null 2>&1 || true
docker run -d --name hc-fastapi-test --network hc-net --env-file /root/hc/hc-fastapi.env \
  "hc-fastapi:$TAG" >/dev/null

OK=0
for i in $(seq 1 20); do
  CODIGO=$(docker run --rm --network hc-net curlimages/curl:latest \
    -s -o /dev/null -w '%{http_code}' --max-time 10 \
    "http://hc-fastapi-test:8000/products/locura?tienda=XBOX" 2>/dev/null || echo 000)
  if [ "$CODIGO" = "200" ]; then OK=1; echo "   el endpoint nuevo responde 200"; break; fi
  sleep 3
done
if [ "$OK" -ne 1 ]; then
  echo "ERROR: el candidato no responde (ultimo codigo: $CODIGO). Registros:"
  docker logs --tail 40 hc-fastapi-test || true
  docker rm -f hc-fastapi-test >/dev/null 2>&1 || true
  echo "Produccion NO se toco."
  exit 1
fi
docker rm -f hc-fastapi-test >/dev/null 2>&1 || true

echo "== 4/4 Promoviendo a produccion"
bash /root/deploy_hc.sh hc-fastapi promote "$TAG"
docker ps --filter name=hc-fastapi --format "   {{.Names}} {{.Status}}"

if command -v curl >/dev/null 2>&1; then
  for i in $(seq 1 20); do
    C=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 https://api.hardcoregames.co/products/week-offers || echo 000)
    case "$C" in 200|301|302) echo "   la API responde ($C)"; break ;; esac
    sleep 3
  done
  if [ "$C" != "200" ] && [ "$C" != "301" ] && [ "$C" != "302" ]; then
    echo "ERROR: la API no responde tras promover (ultimo codigo: $C). Revirtiendo."
    bash /root/deploy_hc.sh hc-fastapi rollback
    exit 1
  fi
fi

echo
echo "Listo. Rollback si hiciera falta: bash /root/deploy_hc.sh hc-fastapi rollback"
