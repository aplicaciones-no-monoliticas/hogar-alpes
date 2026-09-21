# Un repositorio ECR por imagen (FR-004): las seis imágenes se publican acá,
# etiquetadas con el hash corto del commit, nunca con "latest" (R5-15).
# Vive en el mismo Terraform que el clúster porque su ciclo de vida es el
# mismo (se crea una vez, se destruye junto con todo lo demás — CA-3.7).

locals {
  imagenes = [
    "gestion-trabajos",
    "operaciones",
    "acreditacion",
    "emparejamiento",
    "saga-log",
    "bff",
  ]
}

resource "aws_ecr_repository" "hogar_alpes" {
  for_each             = toset(local.imagenes)
  name                 = "hogar-alpes/${each.value}"
  image_tag_mutability = "IMMUTABLE"
  # Entorno efímero (se destruye después de cada verificación, R5-14): sin
  # esto, `terraform destroy` falla con "repository not empty" en vez de
  # limpiar las imágenes que el propio despliegue publicó.
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = { Proyecto = "hogar-alpes" }
}

output "ecr_repositorios" {
  value = { for k, r in aws_ecr_repository.hogar_alpes : k => r.repository_url }
}
