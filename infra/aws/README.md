# Despliegue en AWS — DEP-1

Plan técnico §6.2. Un artefacto: lo que corre en el portátil del equipo es lo
que corre en la nube — mismo `docker compose up`, sin un `docker-compose.prod.yml`
distinto.

## Por qué EC2 + Compose (no ECS, EKS, ni Pulsar gestionado)

- **Mismo artefacto en local y en la nube.** Con el plazo de la entrega, eso
  elimina una clase entera de fallas ("funciona en mi máquina").
- **ECS/EKS** exigen volúmenes persistentes para los bookies y un chart de
  Pulsar pesado — no cabe en el plazo.
- **Pulsar gestionado** (p. ej. StreamNative) contradice el ítem de la
  rúbrica: el clúster lo debe configurar y desplegar el equipo (RNF-2).

## 1. Lanzar la instancia

| Aspecto | Valor |
|---|---|
| Tipo | `t3.xlarge` (4 vCPU, 16 GB) — `t3.large` (8 GB) si AWS Academy no permite xlarge, con la contingencia de Pulsar standalone (plan técnico §10) |
| AMI | Ubuntu 24.04 LTS |
| Disco | gp3, 40 GB |
| Security group | ver abajo |
| User data | `infra/aws/user-data.sh` (pegar el contenido del archivo en el campo "User data" al lanzar la instancia) |

## 2. Security group

| Puerto | Origen | Para qué |
|---|---|---|
| 22 (SSH) | Solo las IP del equipo | Administración |
| 8000-8003 | `0.0.0.0/0` durante la sustentación; si no, solo las IP del equipo | Las cuatro API (trabajos, operaciones, acreditación, emparejamiento) |
| 6650, 6651, 8080, 8081, 5432 y los puertos de PostgreSQL | **Nadie** | Pulsar y las bases de datos **no se exponen**: su administración va por SSH (`docker compose exec`) |

## 3. Primer arranque

Si no se usó `user-data.sh` al lanzar la instancia, se corre a mano por SSH:

```bash
curl -fsSL https://raw.githubusercontent.com/aplicaciones-no-monoliticas/hogar-alpes/main/infra/aws/user-data.sh | bash
```

Genera `.env` con una contraseña propia de la instancia (no la del repositorio)
y levanta `docker compose up -d`. Los primeros minutos: ZooKeeper, los bookies
y los brokers arrancan, `pulsar-config` crea la topología, y las cuatro
imágenes se construyen. `docker compose ps` debe mostrar todo `healthy` o
`running`.

## 4. Verificar desde fuera

```bash
curl http://<IP-PÚBLICA>:8000/health   # gestion-trabajos
curl http://<IP-PÚBLICA>:8001/health   # operaciones
curl http://<IP-PÚBLICA>:8002/health   # acreditacion
curl http://<IP-PÚBLICA>:8003/health   # emparejamiento
```

Y con Postman: entorno `aws` (`postman/hogar-alpes-aws.postman_environment.json`),
reemplazando `<IP-PUBLICA-EC2>` por la IP real de la instancia.

## 5. Costo y apagado

≈ USD 0,17/h en `us-east-1` (t3.xlarge) → ≈ USD 4/día. **Se detiene cuando no
se usa**:

```bash
# Detener sin perder los datos (los volúmenes persisten)
docker compose stop
# O, desde la consola de AWS: Stop instance (no Terminate)
```

## 6. Sin secretos en el repositorio (RNF-6)

- `.env` se genera **en la instancia** (`user-data.sh`), nunca se commitea —
  está en `.gitignore` desde la raíz del repositorio.
- Nada de la VM (IP, claves SSH, credenciales) va al repositorio público.
  Este README no lleva ninguna IP real: se sustituye a mano al usarlo.
