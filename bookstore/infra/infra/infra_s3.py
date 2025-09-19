from aws_cdk import (
    Stack,
    CfnParameter,
    CfnOutput,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
    aws_elasticloadbalancingv2 as elbv2,
    aws_s3 as s3,
)
from aws_cdk import aws_elasticloadbalancingv2_targets as elbv2_targets
from constructs import Construct


class InfraS3Stack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        key_name = CfnParameter(
            self,
            "KeyName",
            type="String",
            default="llave1.pem",
            description="Existing EC2 KeyPair name for SSH (bastion, backend)",
        )
        backend_image = CfnParameter(
            self,
            "BackendImage",
            type="String",
            default="davidlondo/back-bookstore:tagname",
            description="Backend Docker image repo:tag",
        )

        vpc = ec2.Vpc(
            self,
            "BookstoreVpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
                ec2.SubnetConfiguration(name="private-back", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=24),
            ],
        )

        sg_bastion = ec2.SecurityGroup(self, "SgBastion", vpc=vpc, description="Bastion SG", allow_all_outbound=True)
        sg_bastion.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(22), "SSH from anywhere (demo)")

        sg_alb_back = ec2.SecurityGroup(self, "SgAlbBack", vpc=vpc, description="Backend ALB SG internal", allow_all_outbound=True)

        sg_backend = ec2.SecurityGroup(self, "SgBackend", vpc=vpc, description="Backend instance SG", allow_all_outbound=True)
        sg_backend.add_ingress_rule(sg_alb_back, ec2.Port.tcp(5001), "Back ALB to backend")
        sg_backend.add_ingress_rule(sg_bastion, ec2.Port.tcp(22), "SSH from bastion")

        instance_role = iam.Role.from_role_name(self, "ImportedLabRole", role_name="LabRole")

        books_table = dynamodb.Table(
            self,
            "BooksTable",
            table_name="tb_books",
            partition_key=dynamodb.Attribute(name="id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        )

        ubuntu = ec2.MachineImage.from_ssm_parameter(
            "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id",
            os=ec2.OperatingSystemType.LINUX,
        )

        back_group = vpc.select_subnets(subnet_group_name="private-back")
        if len(back_group.subnets) < 2:
            raise ValueError("Expected at least 2 'private-back' subnets (across AZs) for ALB.")

        back_subnet_sel = ec2.SubnetSelection(subnets=[back_group.subnets[0]])

        backend_user_data = ec2.UserData.for_linux()
        backend_user_data.add_commands(
            "set -euxo pipefail",
            "apt update -y",
            "apt upgrade -y",
            "apt install -y ca-certificates curl gnupg lsb-release",
            "install -m 0755 -d /etc/apt/keyrings",
            "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg",
            "chmod a+r /etc/apt/keyrings/docker.gpg",
            'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list',
            "apt update -y",
            "apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin",
            "systemctl enable docker",
            "systemctl start docker",
            f"docker pull {backend_image.value_as_string}",
            f"docker run -d --name backend -p 5001:5001 {backend_image.value_as_string}",
        )
        backend_instance = ec2.Instance(
            self,
            "BackendInstance",
            vpc=vpc,
            vpc_subnets=back_subnet_sel,
            instance_type=ec2.InstanceType("t3.micro"),
            machine_image=ubuntu,
            role=instance_role,
            security_group=sg_backend,
            key_name=key_name.value_as_string,
            user_data=backend_user_data,
        )

        alb_backend = elbv2.ApplicationLoadBalancer(
            self,
            "BackendAlb",
            vpc=vpc,
            internet_facing=True,
            security_group=sg_alb_back,
            vpc_subnets=ec2.SubnetSelection(subnets=back_group.subnets[:2]),
        )
        listener_back = alb_backend.add_listener(
            "BackListener", port=5001, protocol=elbv2.ApplicationProtocol.HTTP, open=False
        )
        listener_back.add_targets(
            "BackTargets",
            port=5001,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[elbv2_targets.InstanceTarget(backend_instance, port=5001)],
            health_check=elbv2.HealthCheck(path="/healthz", port="5001", healthy_http_codes="200"),
        )

        # Allow public HTTP to the API ALB (demo). In production, restrict to CloudFront/allowed clients.
        sg_alb_back.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(5001), "Public to backend ALB (API)")
        sg_alb_back.add_ingress_rule(sg_bastion, ec2.Port.tcp(5001), "Bastion to backend ALB")

        frontend_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            website_index_document="index.html",
            website_error_document="index.html",  # SPA fallback (opcional pero útil)
            public_read_access=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ACLS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Outputs
        CfnOutput(self, "FrontendUrl", value=frontend_bucket.bucket_website_url, description="Frontend S3 URL")
        CfnOutput(self, "FrontendBucketName", value=frontend_bucket.bucket_name)
        CfnOutput(self, "BackendAlbDns", value=alb_backend.load_balancer_dns_name, description="Backend ALB DNS")
        CfnOutput(self, "BooksTableName", value=books_table.table_name)

