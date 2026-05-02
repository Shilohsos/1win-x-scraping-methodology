# Proxy Configuration

## SA Residential Proxy (Current)
| Parameter | Value |
|-----------|-------|
| Host | 82.29.245.95 |
| Port | 6919 |
| Username | pzxyatji |
| Password | tqz8zcybhmj7 |
| Protocol | HTTP |
| Location | South Africa |

## Format
```
http://username:password@host:port
```

## Environment Variable
```bash
export ONEWIN_PROXY="http://pzxyatji:tqz8zcybhmj7@82.29.245.95:6919"
```

## Verification
```python
# Via CloakBrowser
page.goto("https://api.ipify.org")
ip = page.inner_text("body").strip()
assert "82.29.245" in ip

# Via curl
curl -x http://pzxyatji:tqz8zcybhmj7@82.29.245.95:6919 https://api.ipify.org
```

## Security
- Store proxy credentials in `.env` file only
- Never hardcode in scripts
- Set file permissions: `chmod 600 .env`
