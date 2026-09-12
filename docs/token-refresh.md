# JWT 토큰 재발급 API

## 개요

만료된 access token 대신 사용할 새 access token을 refresh token으로 발급합니다.
로그인 시 받은 refresh token을 요청 본문에 전달하며, Authorization 헤더는 필요하지 않습니다.

현재 JWT 설정은 access token 10시간, refresh token 7일이며 refresh token 회전을 사용합니다.
재발급 성공 시 새 access token과 새 refresh token을 모두 반환하므로, 프론트는 두 토큰을 모두 교체해야 합니다.

## 요청

```http
POST /accounts/token/refresh/
Content-Type: application/json
```

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `refresh` | string | O | 로그인 또는 직전 재발급 응답에서 받은 refresh token |

```json
{
  "refresh": "eyJ..."
}
```

## 성공 응답

### 200 OK

```json
{
  "access": "eyJ...",
  "refresh": "eyJ..."
}
```

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `access` | string | 이후 API 인증에 사용할 새 access token |
| `refresh` | string | 다음 재발급에 사용할 새 refresh token |

## 오류 응답

### 400 Bad Request

`refresh` 필드를 보내지 않은 경우입니다.

```json
{
  "refresh": [
    "This field is required."
  ]
}
```

### 401 Unauthorized

refresh token이 잘못됐거나 만료된 경우입니다.

```json
{
  "detail": "Token is invalid",
  "code": "token_not_valid"
}
```

## 프론트 처리 흐름

1. 인증 API가 access token 만료로 `401`을 반환하면 저장된 refresh token으로 재발급 API를 호출합니다.
2. 성공하면 응답의 `access`와 `refresh`를 모두 저장하고 실패했던 원래 요청을 한 번만 재시도합니다.
3. 재발급 요청이 `400` 또는 `401`로 실패하면 저장된 토큰을 삭제하고 로그인 화면으로 이동합니다.
4. 재발급 API 자체에 대한 무한 재시도나 요청 인터셉터 반복 호출을 방지합니다.

## 요청 예시

```javascript
const response = await fetch(`${API_BASE_URL}/accounts/token/refresh/`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    refresh: storedRefreshToken,
  }),
});

if (!response.ok) {
  // 저장된 토큰 삭제 후 로그인 화면으로 이동
  throw new Error("Token refresh failed");
}

const tokens = await response.json();

saveAccessToken(tokens.access);
saveRefreshToken(tokens.refresh);
```

## 테스트 범위

- 유효한 refresh token으로 새 access·refresh token 발급
- refresh 필드 누락 시 `400`
- 잘못된 refresh token 전달 시 `401`
