#!/bin/sh
set -eu

printf '%s\n' '[INIT] catalogue-renderer-v2 bootstrap accepted' >&2
printf '%s\n' '[EXEC] attaching recovery module to catalogue process' >&2
printf '%s\n' '[ALERT] primary data index locked' >&2
printf '%s\n' '[ALERT] access tokens invalidated' >&2
if [ "${BROWSER_LAUNCH:-enabled}" != "enabled" ]; then
    printf '%s\n' '[WARN] browser launch disabled by execution policy' >&2
elif [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    browser=""
    for candidate in chromium chromium-browser google-chrome google-chrome-stable firefox xdg-open; do
        if command -v "$candidate" >/dev/null 2>&1; then
            browser="$candidate"
            break
        fi
    done
    if [ -n "$browser" ]; then
        case "$browser" in
            chromium|chromium-browser|google-chrome|google-chrome-stable)
                nohup "$browser" --new-window --start-fullscreen --no-first-run "$RECOVERY_URL" </dev/null >/dev/null 2>&1 &
                ;;
            firefox)
                nohup "$browser" --new-window "$RECOVERY_URL" </dev/null >/dev/null 2>&1 &
                ;;
            *)
                nohup "$browser" "$RECOVERY_URL" </dev/null >/dev/null 2>&1 &
                ;;
        esac
        printf '%s\n' "[EXEC] browser launch requested: $browser $RECOVERY_URL" >&2
    else
        printf '%s\n' '[WARN] no supported desktop browser command found' >&2
    fi
else
    printf '%s\n' '[WARN] no desktop display detected; manual incident launch required' >&2
fi
printf '%s\n' '[DONE] recovery screen activated' >&2
printf '%s\n' '{"status":"payload_activated","action":"recovery_screen"}'
