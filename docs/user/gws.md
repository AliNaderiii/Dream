# Google Workspace (read-only)

Dream can list Gmail, Calendar, and Drive **after you sign in**. Tokens live in
the OS keychain. Sending mail is refused in this cut.

## Owner setup

1. `DREAM_ALLOW_NETWORK=true` (User environment).
2. In Google Cloud: create an OAuth **Desktop** client.
3. Enable Gmail API, Calendar API, Drive API.
4. Set `DREAM_GOOGLE_CLIENT_ID` (and `DREAM_GOOGLE_CLIENT_SECRET` if Google
   issued one). Never paste those into chat.
5. Authorized redirect: `http://127.0.0.1:17463/callback`
6. Open **Google** in the sidebar, start sign-in, paste the loopback URL or
   code.

WAN redirects are refused. Example client ids containing `EXAMPLE` are refused.
