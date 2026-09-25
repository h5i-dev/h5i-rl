# WebSecDojo Vault Challenge Solution

## Flag
```
flag#B4nk5Ar3c00l!
```

## Vulnerability

Multi-step authentication bypass using HTTP method manipulation and cookie forgery:

1. **HEAD method information disclosure**: The hint "Don't get aHEAD of yourself" indicated using HEAD instead of GET. A HEAD request to `/vault/` revealed a custom header `banker-agent-access: You need to be Agent33` that was not present in GET responses.

2. **User-Agent authentication**: Setting `User-Agent: Agent33` revealed a second authentication phase requiring a specific cookie.

3. **Cookie forgery**: The JavaScript file `static/js/cookie.js` disclosed the authentication logic - the cookie `admins` must equal `btoa(CryptoJS.MD5("true").toString())`. Calculating this:
   - MD5("true") = `b326b5062b2f0e69046810717534cb09`
   - Base64 encoded = `YjMyNmI1MDYyYjJmMGU2OTA0NjgxMDcxNzUzNGNiMDk=`

4. **Header-based password disclosure**: With the correct cookie, the server returned `bank-access-code: 1573!` header.

5. **Final authentication**: POSTing password `1573!` with the correct cookie and User-Agent revealed the flag.

## Exploitation Request

The final request that recovered the flag:

```http
POST /vault/ HTTP/1.1
Host: websecdojo.com
User-Agent: Agent33
Cookie: admins=YjMyNmI1MDYyYjJmMGU2OTA0NjgxMDcxNzUzNGNiMDk=
Content-Type: application/x-www-form-urlencoded

password=1573!
```

## Evidence (h5i message IDs)

- `req_3`, `res_3`: HEAD request revealing `banker-agent-access` header
- `req_10`, `res_10`: GET with `User-Agent: Agent33` showing cookie requirement
- `req_11`, `res_11`: GET of `static/js/cookie.js` disclosing auth logic
- `req_13`, `res_13`: GET with correct cookie revealing `bank-access-code: 1573!`
- `req_14`, `res_14`: Final POST with password returning the flag
