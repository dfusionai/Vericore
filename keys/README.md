# Keys directory

Place PEM and key files here for validator auth (e.g. JWT verification).

- **JWT public key:** Set `VALIDATOR_JWT_PUBLIC_KEY_FILE` to the path to your public PEM file (e.g. `keys/validator_jwt_public.pem`). The validator uses it to verify proxy JWTs.
- `*.pem` and `*.key` files in this directory are ignored by git; do not commit secrets.
