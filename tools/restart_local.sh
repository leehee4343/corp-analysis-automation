#!/bin/bash
# (macOS 개발용) 코드를 고친 뒤 로컬 서버를 다시 띄울 때 쓴다. 사용: tools/restart_local.sh
# 기업분석 시스템 로컬 서비스 재시작: 기존 서버 종료 → 새로 실행 → 응답 확인 → 기존 서버가 돌던(이제 빈) 터미널 창 닫기.
# 실행 중인 프로세스가 하나도 없는(이미 끝난) 창만 닫는다 — 다른 프로젝트의 실행 중인 창은 건드리지 않음.
# (창 제목의 한글은 macOS에서 NFD라 이름 비교는 쓰지 않는다)
APP="$(cd "$(dirname "$0")/.." && pwd)"
PORT=8700
for pid in $(lsof -ti tcp:$PORT -sTCP:LISTEN); do kill "$pid" 2>/dev/null; done
for i in $(seq 1 30); do lsof -ti tcp:$PORT -sTCP:LISTEN >/dev/null || break; sleep 0.3; done
touch /tmp/corp-analysis-no-browser  # 재시작 때는 브라우저 탭을 새로 열지 않음
open "$APP/프로그램 시작.command"
ok=0
for i in $(seq 1 60); do curl -sf -o /dev/null "http://127.0.0.1:$PORT/api/session" && { ok=1; break; }; sleep 0.5; done
sleep 1
osascript -e 'tell application "Terminal"
  set ids to {}
  repeat with w in windows
    try
      if (not (busy of tab 1 of w)) and ((count of (processes of tab 1 of w)) = 0) then set end of ids to id of w
    end try
  end repeat
  repeat with i in ids
    try
      close (first window whose id is i) saving no
    end try
  end repeat
end tell' >/dev/null 2>&1
[ $ok = 1 ] && echo "started: pid $(lsof -ti tcp:$PORT -sTCP:LISTEN)" || { echo "server did not respond"; exit 1; }
