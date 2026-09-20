# DEP-1 · Infraestructura como código — despliegue de Hogar de los Alpes en AWS.
#
# Una EC2 en una VPC propia (10.42.0.0/16, una subred pública), con un
# security group que expone solo lo que el plan técnico §6.2 pide (SSH
# restringido, 8000-8003 para las cuatro API) y `infra/aws/user-data.sh` como
# aprovisionamiento.
#
# Por qué VPC propia y no la VPC "default" de la cuenta: algunas cuentas
# (esta incluida) no tienen ninguna VPC por defecto — `data.aws_vpc.default`
# falla con "no matching EC2 VPC found". Crear la VPC aquí hace el despliegue
# independiente de ese detalle de la cuenta.
#
#   terraform init
#   terraform apply -var="ssh_cidr=<TU-IP>/32"
#   ...
#   terraform destroy -var="ssh_cidr=<TU-IP>/32"   # tira todo abajo, limpio, cuando ya no se necesita

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  description = "Región de AWS"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "t3.xlarge por defecto (plan técnico §6.2); t3.large si la cuenta no lo permite"
  type        = string
  default     = "t3.xlarge"
}

variable "ssh_cidr" {
  description = "CIDR permitido para SSH (22). Restringir a las IP del equipo."
  type        = string
}

variable "ssh_public_key_path" {
  description = <<-EOT
    Ruta a la llave pública SSH que se registra como aws_key_pair para poder
    entrar por SSH a la instancia (necesario para correr escenarios/*.sh a
    mano, ver infra/aws/README.md §5). Generar una dedicada al proyecto:

      ssh-keygen -t ed25519 -f ~/.ssh/hogar-alpes -C hogar-alpes -N ""
  EOT
  type        = string
  default     = "~/.ssh/hogar-alpes.pub"
}

variable "exponer_pulsar_manager" {
  description = <<-EOT
    Abre el puerto 9527 (Pulsar Manager) a 0.0.0.0/0 — SOLO para la sesión de
    demo/sustentación. Por defecto false: el panel de administración de
    Pulsar no tiene autenticación fuerte (usuario/clave que crea
    infra/pulsar/pulsar-manager-setup.sh), así que dejarlo abierto de forma
    permanente no es lo que se quiere. Flujo recomendado:

      terraform apply -var="exponer_pulsar_manager=true" -var="ssh_cidr=..."
      # ... hacer la demo ...
      terraform apply -var="exponer_pulsar_manager=false" -var="ssh_cidr=..."

    Ninguno de los dos comandos recrea la instancia — solo agrega o quita
    esta única regla del security group.
  EOT
  type        = bool
  default     = false
}

variable "exponer_grafana" {
  description = <<-EOT
    Abre el puerto 3000 (Grafana) a 0.0.0.0/0 — SOLO para la sesión de
    demo/sustentación, mismo patrón que exponer_pulsar_manager. Por defecto
    false: la clave de admin es la de GRAFANA_PASSWORD (o el valor por
    defecto de docker-compose.yml), y no hay razón para dejarla accesible
    fuera de la demo.

      terraform apply -var="exponer_grafana=true" -var="ssh_cidr=..."
      # ... hacer la demo ...
      terraform apply -var="exponer_grafana=false" -var="ssh_cidr=..."
  EOT
  type        = bool
  default     = false
}

# No toda zona de disponibilidad ofrece todos los tipos de instancia (nos
# pasó con t3.xlarge en us-east-1e) — se filtran las zonas donde el tipo
# elegido SÍ está disponible, y ahí se crea la subred.
data "aws_ec2_instance_type_offerings" "disponibles" {
  filter {
    name   = "instance-type"
    values = [var.instance_type]
  }
  location_type = "availability-zone"
}

resource "aws_vpc" "hogar_alpes" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name     = "hogar-alpes"
    Proyecto = "hogar-alpes"
  }
}

resource "aws_subnet" "publica" {
  vpc_id                  = aws_vpc.hogar_alpes.id
  cidr_block              = "10.42.1.0/24"
  availability_zone       = data.aws_ec2_instance_type_offerings.disponibles.locations[0]
  map_public_ip_on_launch = true

  tags = {
    Name     = "hogar-alpes-publica"
    Proyecto = "hogar-alpes"
  }

  # El orden de `locations` no es estable entre llamadas al API — sin esto,
  # un `plan` cualquiera (incluso solo para abrir un puerto del security
  # group) puede "descubrir" una zona distinta y forzar el reemplazo de la
  # subred, la asociación de la route table y la instancia completa.
  lifecycle {
    ignore_changes = [availability_zone]
  }
}

resource "aws_internet_gateway" "hogar_alpes" {
  vpc_id = aws_vpc.hogar_alpes.id

  tags = {
    Name     = "hogar-alpes"
    Proyecto = "hogar-alpes"
  }
}

resource "aws_route_table" "publica" {
  vpc_id = aws_vpc.hogar_alpes.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.hogar_alpes.id
  }

  tags = {
    Name     = "hogar-alpes-publica"
    Proyecto = "hogar-alpes"
  }
}

resource "aws_route_table_association" "publica" {
  subnet_id      = aws_subnet.publica.id
  route_table_id = aws_route_table.publica.id
}

resource "aws_key_pair" "hogar_alpes" {
  key_name   = "hogar-alpes"
  public_key = file(pathexpand(var.ssh_public_key_path))

  tags = {
    Proyecto = "hogar-alpes"
  }
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
  filter {
    name   = "state"
    values = ["available"]
  }
}

resource "aws_security_group" "hogar_alpes" {
  name        = "hogar-alpes-sg"
  description = "Hogar de los Alpes - Entrega 4 (DEP-1)"
  vpc_id      = aws_vpc.hogar_alpes.id

  ingress {
    description = "SSH desde el equipo"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_cidr]
  }

  ingress {
    description = "Las cuatro API, durante la sustentacion"
    from_port   = 8000
    to_port     = 8003
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Pulsar (6650-6651, 8080-8081) y PostgreSQL NUNCA se exponen — sin regla
  # de ingreso para ellos. Su administración va por SSH (docker compose exec).
  # Pulsar Manager (9527) es la única excepción, y solo cuando
  # exponer_pulsar_manager=true — ver esa variable y la regla aparte abajo.

  tags = {
    Name     = "hogar-alpes-sg"
    Proyecto = "hogar-alpes"
  }
}

# Regla separada (no un bloque `ingress` más del recurso de arriba) para que
# activarla/desactivarla sea un cambio de una sola regla, no un diff del
# security group completo cada vez que se prende y se apaga para la demo.
# El BFF (US-02): un solo punto de entrada. Regla aparte y no otra entrada del
# bloque `ingress` de las cuatro API, para que se pueda quitar sin tocarlo.
resource "aws_security_group_rule" "bff" {
  type              = "ingress"
  security_group_id = aws_security_group.hogar_alpes.id
  from_port         = 8090
  to_port           = 8090
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "BFF - un solo punto de entrada (US-02)"
}

resource "aws_security_group_rule" "pulsar_manager_demo" {
  count             = var.exponer_pulsar_manager ? 1 : 0
  type              = "ingress"
  security_group_id = aws_security_group.hogar_alpes.id
  from_port         = 9527
  to_port           = 9527
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "Pulsar Manager - SOLO durante la demo (exponer_pulsar_manager=true)"
}

resource "aws_security_group_rule" "grafana_demo" {
  count             = var.exponer_grafana ? 1 : 0
  type              = "ingress"
  security_group_id = aws_security_group.hogar_alpes.id
  from_port         = 3000
  to_port           = 3000
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "Grafana - SOLO durante la demo (exponer_grafana=true)"
}

resource "aws_instance" "hogar_alpes" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.publica.id
  key_name               = aws_key_pair.hogar_alpes.key_name
  vpc_security_group_ids = [aws_security_group.hogar_alpes.id]
  user_data              = file("${path.module}/../user-data.sh")

  root_block_device {
    volume_size           = 40
    volume_type           = "gp3"
    delete_on_termination = true
  }

  tags = {
    Name     = "hogar-alpes-entrega4"
    Proyecto = "hogar-alpes"
  }
}

output "instance_id" {
  value = aws_instance.hogar_alpes.id
}

output "public_ip" {
  value = aws_instance.hogar_alpes.public_ip
}

output "ssh" {
  value = "ssh -i ${var.ssh_public_key_path == "~/.ssh/hogar-alpes.pub" ? "~/.ssh/hogar-alpes" : trimsuffix(var.ssh_public_key_path, ".pub")} ubuntu@${aws_instance.hogar_alpes.public_ip}"
}

output "urls" {
  value = {
    gestion_trabajos = "http://${aws_instance.hogar_alpes.public_ip}:8000/health"
    operaciones      = "http://${aws_instance.hogar_alpes.public_ip}:8001/health"
    acreditacion     = "http://${aws_instance.hogar_alpes.public_ip}:8002/health"
    emparejamiento   = "http://${aws_instance.hogar_alpes.public_ip}:8003/health"
    bff              = "http://${aws_instance.hogar_alpes.public_ip}:8090/health"
  }
}

output "pulsar_manager_url" {
  description = "Solo resuelve algo útil si exponer_pulsar_manager=true y el contenedor está arriba (docker compose --profile demo up -d pulsar-manager + infra/pulsar/pulsar-manager-setup.sh, por SSH)"
  value       = "http://${aws_instance.hogar_alpes.public_ip}:9527"
}

output "grafana_url" {
  description = "Solo resuelve algo útil si exponer_grafana=true y el contenedor está arriba (docker compose --profile demo up -d prometheus grafana, por SSH)"
  value       = "http://${aws_instance.hogar_alpes.public_ip}:3000"
}
