from aws_cdk import (
    Stack,
    CfnParameter,
    CfnOutput,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
    aws_elasticloadbalancingv2 as elbv2,
)
from aws_cdk import aws_elasticloadbalancingv2_targets as elbv2_targets
from aws_cdk import aws_autoscaling as autoscaling
from constructs import Construct


class InfraStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        key_name = CfnParameter(
            self,
            "KeyName",
            type="String",
            default="llave1.pem",
            description="Existing EC2 KeyPair name for SSH (bastion, frontend, backend)",
        )
        backend_image = CfnParameter(
            self,
            "BackendImage",
            type="String",
            default="davidlondo/back-bookstore:tagname",
            description="Backend Docker image repo:tag",
        )
        frontend_image = CfnParameter(
            self,
            "FrontendImage",
            type="String",
            default="davidlondo/front-bookstore:v5",
            description="Frontend Docker image repo:tag",
        )

        vpc = ec2.Vpc(
            self,
            "BookstoreVpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
                ec2.SubnetConfiguration(name="private-front", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=24),
                ec2.SubnetConfiguration(name="private-back", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=24),
            ],
        )

        sg_bastion = ec2.SecurityGroup(self, "SgBastion", vpc=vpc, description="Bastion SG", allow_all_outbound=True)
        sg_bastion.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(22), "SSH from anywhere (demo)")

        sg_alb_front = ec2.SecurityGroup(self, "SgAlbFront", vpc=vpc, description="Frontend ALB SG", allow_all_outbound=True)
        sg_alb_front.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "HTTP public")

        sg_alb_back = ec2.SecurityGroup(self, "SgAlbBack", vpc=vpc, description="Backend ALB SG internal", allow_all_outbound=True)

        sg_frontend = ec2.SecurityGroup(self, "SgFrontend", vpc=vpc, description="Frontend instance SG", allow_all_outbound=True)
        sg_frontend.add_ingress_rule(sg_alb_front, ec2.Port.tcp(80), "Front ALB to frontend")
        sg_frontend.add_ingress_rule(sg_bastion, ec2.Port.tcp(22), "SSH from bastion")

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

        front_group = vpc.select_subnets(subnet_group_name="private-front")
        back_group = vpc.select_subnets(subnet_group_name="private-back")
        if len(front_group.subnets) == 0 or len(back_group.subnets) < 2:
            raise ValueError("Expected at least 1 'private-front' subnet and 2 'private-back' subnets (across AZs) for ALB.")
        front_subnet_sel = ec2.SubnetSelection(subnets=[front_group.subnets[0]])
        back_subnet_sel = ec2.SubnetSelection(subnets=[back_group.subnets[0]])

        backend_user_data = ec2.UserData.for_linux()
        backend_user_data.add_commands(
            "#!/bin/bash",
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
        
        backend_asg = autoscaling.AutoScalingGroup(
            self,
            "BackendAsg",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_group_name="private-back"),
            instance_type=ec2.InstanceType("t3.micro"),
            machine_image=ubuntu,
            role=instance_role,
            security_group=sg_backend,
            key_name=key_name.value_as_string,
            min_capacity=2,
            max_capacity=4,
            desired_capacity=2,
            user_data=backend_user_data,
        )

        all_private = vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS).subnets
        preferred_order = back_group.subnets + [s for s in all_private if s not in back_group.subnets]
        distinct_az_subnets = []
        seen_az = set()
        for s in preferred_order:
            if s.availability_zone not in seen_az:
                distinct_az_subnets.append(s)
                seen_az.add(s.availability_zone)
            if len(distinct_az_subnets) == 2:
                break
        if len(distinct_az_subnets) < 2:
            raise ValueError(
                "Unable to find two private subnets in distinct AZs for Backend ALB. "
                "Deploy in a region with at least 2 AZs or adjust design (e.g., remove internal ALB)."
            )
        if len(back_group.subnets) < 2:
            self.node.add_warning(
                "Only one 'private-back' subnet available; using an additional private subnet from another group to satisfy ALB multi-AZ requirement."
            )

        alb_backend = elbv2.ApplicationLoadBalancer(
            self,
            "BackendAlb",
            vpc=vpc,
            internet_facing=False,
            security_group=sg_alb_back,
            vpc_subnets=ec2.SubnetSelection(subnets=distinct_az_subnets),
        )
        listener_back = alb_backend.add_listener(
            "BackListener", port=5001, protocol=elbv2.ApplicationProtocol.HTTP, open=False
        )
        listener_back.add_targets(
            "BackTargets",
            port=5001,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[backend_asg],
            health_check=elbv2.HealthCheck(path="/healthz", port="5001", healthy_http_codes="200"),
        )

        sg_alb_back.add_ingress_rule(sg_alb_front, ec2.Port.tcp(5001), "Front ALB to backend ALB")

        frontend_user_data = ec2.UserData.for_linux()
        frontend_user_data.add_commands(
            "#!/bin/bash",
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
            f"docker pull {frontend_image.value_as_string}",
            f"docker run -d --name frontend -p 80:80 {frontend_image.value_as_string}",
        )
        frontend_asg = autoscaling.AutoScalingGroup(
            self,
            "FrontendAsg",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_group_name="private-front"),
            instance_type=ec2.InstanceType("t3.micro"),
            machine_image=ubuntu,
            role=instance_role,
            security_group=sg_frontend,
            key_name=key_name.value_as_string,
            min_capacity=2,
            max_capacity=4,
            desired_capacity=2,
            user_data=frontend_user_data,
        )

        alb_frontend = elbv2.ApplicationLoadBalancer(
            self,
            "FrontendAlb",
            vpc=vpc,
            internet_facing=True,
            security_group=sg_alb_front,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )
        listener_front = alb_frontend.add_listener(
            "FrontListener", port=80, open=True, protocol=elbv2.ApplicationProtocol.HTTP
        )
        listener_front.add_targets(
            "FrontTargets",
            port=80,
            targets=[frontend_asg],
            health_check=elbv2.HealthCheck(path="/", port="80", healthy_http_codes="200,302,301"),
        )

        backend_tg = elbv2.ApplicationTargetGroup(
            self,
            "BackendTargetGroup",
            vpc=vpc,
            port=5001,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.INSTANCE,
            targets=[backend_asg],
            health_check=elbv2.HealthCheck(path="/healthz", port="5001", healthy_http_codes="200"),
        )

        listener_front.add_action(
            "ApiPathForward",
            priority=10,
            conditions=[elbv2.ListenerCondition.path_patterns(["/api/*"])],
            action=elbv2.ListenerAction.forward([backend_tg]),
        )

        sg_backend.add_ingress_rule(sg_alb_front, ec2.Port.tcp(5001), "Front ALB to backend (API path)")

        bastion = ec2.Instance(
            self,
            "Bastion",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType("t3.micro"),
            machine_image=ubuntu,
            role=instance_role,
            security_group=sg_bastion,
            key_name=key_name.value_as_string,
        )

        # Outputs
        CfnOutput(self, "FrontendAlbDns", value=alb_frontend.load_balancer_dns_name, description="Public ALB DNS")
        CfnOutput(self, "BackendAlbDns", value=alb_backend.load_balancer_dns_name, description="Internal backend ALB DNS")
        CfnOutput(self, "BastionPublicIp", value=bastion.instance_public_ip, description="SSH bastion public IP")
        CfnOutput(self, "BooksTableName", value=books_table.table_name)

