# REST API Design Best Practices

## Resource Naming

Use nouns, not verbs. Resources are things, actions are HTTP methods.

```
GET    /articles          # list articles
GET    /articles/42       # get article 42
POST   /articles          # create a new article
PUT    /articles/42       # replace article 42
PATCH  /articles/42       # partial update of article 42
DELETE /articles/42       # delete article 42
```

Nested resources express ownership:
```
GET /users/7/orders        # orders belonging to user 7
GET /users/7/orders/99     # specific order
```

Keep URLs lowercase, use hyphens (not underscores) for readability.

## Versioning

Version in the URL path is most explicit and cache-friendly:
```
/v1/articles
/v2/articles
```

Alternatives: `Accept: application/vnd.myapi.v2+json` (header versioning) or
`?api_version=2` (query param) — both work but are less visible in logs.

Strategy: never remove fields in a minor version; only add (forward compatibility).
Deprecate endpoints with a `Deprecation` response header before removal.

## Pagination

For large collections, always paginate. Three common patterns:

**Offset-based** (simplest, works with sorting):
```
GET /articles?offset=40&limit=20
```
Response: `{ "data": [...], "total": 1234, "offset": 40, "limit": 20 }`
Con: items can shift if rows are inserted/deleted between pages.

**Cursor-based** (stable for real-time feeds):
```
GET /articles?cursor=eyJpZCI6NDJ9&limit=20
```
Response includes `next_cursor` for the following page.
Pro: consistent even under concurrent writes.

**Page-number** (user-friendly for UIs):
```
GET /articles?page=3&per_page=20
```

Always include `Link` header with `rel=next,prev,first,last` per RFC 5988.

## Error Responses

Use standard HTTP status codes consistently:

| Code | Meaning |
|------|---------|
| 200 OK | Success |
| 201 Created | Resource created (include Location header) |
| 204 No Content | Success, no body (e.g., DELETE) |
| 400 Bad Request | Client sent invalid input |
| 401 Unauthorized | Authentication required |
| 403 Forbidden | Authenticated but not authorised |
| 404 Not Found | Resource does not exist |
| 409 Conflict | State conflict (duplicate, version mismatch) |
| 422 Unprocessable Entity | Valid JSON but fails business validation |
| 429 Too Many Requests | Rate limit exceeded |
| 500 Internal Server Error | Unexpected server fault |

Error response body:
```json
{
  "error": {
    "code": "validation_failed",
    "message": "Email address is already in use",
    "field": "email",
    "request_id": "req_abc123"
  }
}
```

Always include a `request_id` to correlate with server logs.
