# US-03 · Clúster de Kubernetes (EKS) para Hogar de los Alpes.
#
# Independiente de infra/aws/terraform/ (la EC2 con Docker Compose): VPC propia,
# no reutiliza la 10.42.0.0/16 de la EC2. Los dos caminos de despliegue
# coexisten sin pisarse (CA-3.8).
#
#   terraform init
#   terraform apply
#   aws eks update-kubeconfig --name hogar-alpes-eks --region us-east-1
#   ...
#   terraform destroy

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = var.region
}

data "aws_availability_zones" "disponibles" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.disponibles.names, 0, 2)
}

resource "aws_vpc" "hogar_alpes_eks" {
  cidr_block           = "10.43.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name     = "hogar-alpes-eks"
    Proyecto = "hogar-alpes"
  }
}

resource "aws_subnet" "publica" {
  count                   = 2
  vpc_id                  = aws_vpc.hogar_alpes_eks.id
  cidr_block              = "10.43.${count.index}.0/24"
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name                                          = "hogar-alpes-eks-publica-${count.index}"
    Proyecto                                      = "hogar-alpes"
    "kubernetes.io/role/elb"                      = "1"
    "kubernetes.io/cluster/hogar-alpes-eks"       = "shared"
  }
}

resource "aws_internet_gateway" "hogar_alpes_eks" {
  vpc_id = aws_vpc.hogar_alpes_eks.id
  tags = {
    Name     = "hogar-alpes-eks"
    Proyecto = "hogar-alpes"
  }
}

resource "aws_route_table" "publica" {
  vpc_id = aws_vpc.hogar_alpes_eks.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.hogar_alpes_eks.id
  }
  tags = {
    Name     = "hogar-alpes-eks-publica"
    Proyecto = "hogar-alpes"
  }
}

resource "aws_route_table_association" "publica" {
  count          = 2
  subnet_id      = aws_subnet.publica[count.index].id
  route_table_id = aws_route_table.publica.id
}

resource "aws_iam_role" "cluster" {
  name = "hogar-alpes-eks-cluster"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "cluster_policy" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_eks_cluster" "hogar_alpes" {
  name     = "hogar-alpes-eks"
  role_arn = aws_iam_role.cluster.arn
  version  = var.kubernetes_version

  vpc_config {
    subnet_ids              = aws_subnet.publica[*].id
    endpoint_public_access   = true
    endpoint_private_access  = false
  }

  depends_on = [aws_iam_role_policy_attachment.cluster_policy]

  tags = { Proyecto = "hogar-alpes" }
}

resource "aws_iam_role" "node" {
  name = "hogar-alpes-eks-node"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "node_worker" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "node_cni" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "node_ecr" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# El driver CSI de EBS corre en los nodos con la identidad del node role
# (más simple que IRSA para el alcance de esta historia); necesita poder
# crear/adjuntar volúmenes para los PersistentVolumeClaim (FR-016).
resource "aws_iam_role_policy_attachment" "node_ebs_csi" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

resource "aws_eks_node_group" "principal" {
  cluster_name    = aws_eks_cluster.hogar_alpes.name
  node_group_name = "principal"
  node_role_arn   = aws_iam_role.node.arn
  subnet_ids      = aws_subnet.publica[*].id
  instance_types  = [var.instance_type]

  scaling_config {
    desired_size = var.node_count
    min_size     = var.node_min
    max_size     = var.node_max
  }

  depends_on = [
    aws_iam_role_policy_attachment.node_worker,
    aws_iam_role_policy_attachment.node_cni,
    aws_iam_role_policy_attachment.node_ecr,
  ]

  tags = { Proyecto = "hogar-alpes" }
}

resource "aws_eks_addon" "vpc_cni" {
  cluster_name = aws_eks_cluster.hogar_alpes.name
  addon_name   = "vpc-cni"
}

# El controller del driver CSI corre en un pod, no en el nodo: sin IRSA,
# intenta usar IMDS del nodo y falla por el hop-limit por defecto de los
# managed node groups (CrashLoopBackOff, "no EC2 IMDS role found" —
# docs/decisiones.md). El OIDC provider + el rol con IRSA son la forma
# soportada de darle credenciales de AWS a un pod específico.
data "tls_certificate" "eks_oidc" {
  url = aws_eks_cluster.hogar_alpes.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  url             = aws_eks_cluster.hogar_alpes.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks_oidc.certificates[0].sha1_fingerprint]
}

data "aws_iam_policy_document" "ebs_csi_irsa_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.eks.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:sub"
      values   = ["system:serviceaccount:kube-system:ebs-csi-controller-sa"]
    }
  }
}

resource "aws_iam_role" "ebs_csi_irsa" {
  name               = "hogar-alpes-ebs-csi-irsa"
  assume_role_policy = data.aws_iam_policy_document.ebs_csi_irsa_trust.json
}

resource "aws_iam_role_policy_attachment" "ebs_csi_irsa" {
  role       = aws_iam_role.ebs_csi_irsa.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

resource "aws_eks_addon" "ebs_csi" {
  cluster_name             = aws_eks_cluster.hogar_alpes.name
  addon_name               = "aws-ebs-csi-driver"
  service_account_role_arn = aws_iam_role.ebs_csi_irsa.arn
  resolve_conflicts_on_update = "OVERWRITE"
  depends_on               = [aws_eks_node_group.principal]
}

resource "aws_eks_addon" "coredns" {
  cluster_name = aws_eks_cluster.hogar_alpes.name
  addon_name   = "coredns"
  depends_on   = [aws_eks_node_group.principal]
}

resource "aws_eks_addon" "kube_proxy" {
  cluster_name = aws_eks_cluster.hogar_alpes.name
  addon_name   = "kube-proxy"
}

output "cluster_name" {
  value = aws_eks_cluster.hogar_alpes.name
}

output "cluster_endpoint" {
  value = aws_eks_cluster.hogar_alpes.endpoint
}

output "kubeconfig_cmd" {
  value = "aws eks update-kubeconfig --name ${aws_eks_cluster.hogar_alpes.name} --region ${var.region}"
}

output "vpc_id" {
  value = aws_vpc.hogar_alpes_eks.id
}
