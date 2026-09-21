variable "region" {
  description = "Región de AWS"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "Tipo de instancia de los nodos del node group. t3.large por defecto; bajar a t3.medium si la cuenta no lo permite (CA-3.29)"
  type        = string
  default     = "t3.large"
}

variable "node_count" {
  description = "Número de nodos del node group administrado"
  type        = number
  default     = 3
}

variable "node_min" {
  type    = number
  default = 2
}

variable "node_max" {
  type    = number
  default = 4
}

variable "kubernetes_version" {
  type    = string
  default = "1.31"
}
