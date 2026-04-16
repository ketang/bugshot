#!/usr/bin/env bash
set -euo pipefail

# End-to-end test for bugshot gallery server.
# Creates test data, starts the server, exercises all API endpoints,
# and verifies responses.

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMPDIR="$(mktemp -d)"
SERVER_PID=""

cleanup() {
    if [ -n "$SERVER_PID" ]; then
        kill "$SERVER_PID" 2>/dev/null || true
    fi
    rm -rf "$TMPDIR"
}
trap cleanup EXIT

echo "=== Setting up test data ==="
python3 -c "
import os, struct, zlib
def make_png(path):
    raw = b'\x00\xff\x00\x00'
    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(chunk(b'IHDR', ihdr))
        f.write(chunk(b'IDAT', zlib.compress(raw)))
        f.write(chunk(b'IEND', b''))
make_png('$TMPDIR/alpha.png')
make_png('$TMPDIR/beta.png')
"
printf '\x1b[1;31mBold Red Error\x1b[0m\n\x1b[32mGreen OK\x1b[0m\n' > "$TMPDIR/gamma.ansi"

echo "=== Starting server ==="
python3 "$SCRIPT_DIR/gallery_server.py" "$TMPDIR" > "$TMPDIR/server_output.txt" 2>&1 &
SERVER_PID=$!
sleep 1

STARTUP_JSON=$(head -1 "$TMPDIR/server_output.txt")
URL=$(echo "$STARTUP_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin)['url'])")
echo "Server running at $URL"

PASS=0
FAIL=0

check() {
    local name="$1" result="$2"
    if [ "$result" = "true" ]; then
        echo "PASS: $name"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $name"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "=== Testing routes ==="

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL/")
check "Index returns 200" "$([ "$HTTP_CODE" = "200" ] && echo true || echo false)"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL/view/alpha.png")
check "Detail returns 200" "$([ "$HTTP_CODE" = "200" ] && echo true || echo false)"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL/screenshots/alpha.png")
check "Screenshot returns 200" "$([ "$HTTP_CODE" = "200" ] && echo true || echo false)"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL/view/gamma.ansi")
check "ANSI detail returns 200" "$([ "$HTTP_CODE" = "200" ] && echo true || echo false)"

BODY=$(curl -s "$URL/view/gamma.ansi")
check "ANSI content rendered" "$(echo "$BODY" | grep -q "Bold Red Error" && echo true || echo false)"

echo ""
echo "=== Testing comment CRUD ==="

RESP=$(curl -s -X POST "$URL/api/comments" -H "Content-Type: application/json" -d '{"image":"alpha.png","body":"Test issue"}')
check "Comment created" "$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('id')==1 and d.get('body')=='Test issue' else 'false')")"

RESP=$(curl -s "$URL/api/comments")
check "Comment list" "$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if len(d)==1 else 'false')")"

RESP=$(curl -s "$URL/api/comments?image=alpha.png")
check "Comment filter" "$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if len(d)==1 else 'false')")"

RESP=$(curl -s -X PATCH "$URL/api/comments/1" -H "Content-Type: application/json" -d '{"body":"Updated issue"}')
check "Comment updated" "$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('body')=='Updated issue' else 'false')")"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$URL/api/comments/1")
check "Comment deleted" "$([ "$HTTP_CODE" = "204" ] && echo true || echo false)"

echo ""
echo "=== Testing session lifecycle ==="

RESP=$(curl -s -X POST "$URL/api/heartbeat" -H "Content-Type: application/json" -d '{}')
check "Heartbeat" "$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('ok') else 'false')")"

RESP=$(curl -s "$URL/api/status")
check "Status not done" "$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if not d.get('done') else 'false')")"

curl -s -X POST "$URL/api/done" -H "Content-Type: application/json" -d '{}' > /dev/null
RESP=$(curl -s "$URL/api/status")
check "Done after button" "$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('done') and d.get('reason')=='button' else 'false')")"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
