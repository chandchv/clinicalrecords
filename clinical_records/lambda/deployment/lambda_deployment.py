"""
AWS Lambda Deployment Configuration and Scripts

This module provides deployment utilities for AWS Lambda functions,
including infrastructure setup, configuration management, and deployment automation.
"""

import json
import boto3
import zipfile
import os
import tempfile
import shutil
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class LambdaDeploymentManager:
    """
    Manages deployment of Lambda functions and related AWS resources
    """
    
    def __init__(self, aws_region: str = 'us-east-1'):
        """Initialize deployment manager"""
        self.aws_region = aws_region
        
        # AWS clients
        self.lambda_client = boto3.client('lambda', region_name=aws_region)
        self.iam_client = boto3.client('iam', region_name=aws_region)
        self.sqs_client = boto3.client('sqs', region_name=aws_region)
        self.s3_client = boto3.client('s3', region_name=aws_region)
        self.cloudformation_client = boto3.client('cloudformation', region_name=aws_region)
        
        # Configuration
        self.function_name = 'clinical-document-processor'
        self.role_name = 'clinical-document-processor-role'
        self.stack_name = 'clinical-records-lambda-stack'
    
    def create_lambda_package(self, source_dir: str, output_path: str) -> str:
        """
        Create Lambda deployment package
        
        Args:
            source_dir: Directory containing Lambda function code
            output_path: Path for output ZIP file
            
        Returns:
            str: Path to created ZIP file
        """
        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # Add Lambda function code
                lambda_file = os.path.join(source_dir, 'lambda_functions.py')
                if os.path.exists(lambda_file):
                    zip_file.write(lambda_file, 'lambda_function.py')
                
                # Add requirements (if any)
                requirements_file = os.path.join(source_dir, 'requirements.txt')
                if os.path.exists(requirements_file):
                    zip_file.write(requirements_file, 'requirements.txt')
                
                # Add any additional files
                for root, dirs, files in os.walk(source_dir):
                    for file in files:
                        if file.endswith(('.py', '.txt', '.json')):
                            file_path = os.path.join(root, file)
                            arc_name = os.path.relpath(file_path, source_dir)
                            zip_file.write(file_path, arc_name)
            
            logger.info(f"Lambda package created: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error creating Lambda package: {str(e)}")
            raise
    
    def create_iam_role(self) -> str:
        """
        Create IAM role for Lambda function
        
        Returns:
            str: ARN of created role
        """
        try:
            # Trust policy for Lambda
            trust_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "lambda.amazonaws.com"
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }
            
            # Create role
            response = self.iam_client.create_role(
                RoleName=self.role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description='Role for clinical document processing Lambda function'
            )
            
            role_arn = response['Role']['Arn']
            
            # Attach basic Lambda execution policy
            self.iam_client.attach_role_policy(
                RoleName=self.role_name,
                PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
            )
            
            # Create and attach custom policy
            custom_policy = self._create_lambda_policy()
            
            self.iam_client.put_role_policy(
                RoleName=self.role_name,
                PolicyName='ClinicalDocumentProcessingPolicy',
                PolicyDocument=json.dumps(custom_policy)
            )
            
            logger.info(f"IAM role created: {role_arn}")
            return role_arn
            
        except Exception as e:
            logger.error(f"Error creating IAM role: {str(e)}")
            raise
    
    def _create_lambda_policy(self) -> Dict[str, Any]:
        """Create custom IAM policy for Lambda function"""
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "s3:GetObject",
                        "s3:PutObject",
                        "s3:DeleteObject"
                    ],
                    "Resource": [
                        "arn:aws:s3:::clinical-documents/*",
                        "arn:aws:s3:::clinical-documents-*/*"
                    ]
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "sqs:ReceiveMessage",
                        "sqs:DeleteMessage",
                        "sqs:SendMessage",
                        "sqs:GetQueueAttributes"
                    ],
                    "Resource": [
                        "arn:aws:sqs:*:*:clinical-processing-*",
                        "arn:aws:sqs:*:*:clinical-results-*",
                        "arn:aws:sqs:*:*:clinical-dlq-*"
                    ]
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "textract:DetectDocumentText",
                        "textract:AnalyzeDocument"
                    ],
                    "Resource": "*"
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "secretsmanager:GetSecretValue"
                    ],
                    "Resource": [
                        "arn:aws:secretsmanager:*:*:secret:clinical-records-db-*"
                    ]
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents"
                    ],
                    "Resource": "arn:aws:logs:*:*:*"
                }
            ]
        }
    
    def create_sqs_queues(self) -> Dict[str, str]:
        """
        Create SQS queues for Lambda processing
        
        Returns:
            Dict containing queue URLs
        """
        try:
            queue_urls = {}
            
            # Dead letter queue
            dlq_response = self.sqs_client.create_queue(
                QueueName='clinical-processing-dlq',
                Attributes={
                    'MessageRetentionPeriod': '1209600',  # 14 days
                    'VisibilityTimeoutSeconds': '300'
                }
            )
            dlq_url = dlq_response['QueueUrl']
            queue_urls['dead_letter_queue'] = dlq_url
            
            # Get DLQ ARN for redrive policy
            dlq_attrs = self.sqs_client.get_queue_attributes(
                QueueUrl=dlq_url,
                AttributeNames=['QueueArn']
            )
            dlq_arn = dlq_attrs['Attributes']['QueueArn']
            
            # Processing queue
            processing_response = self.sqs_client.create_queue(
                QueueName='clinical-processing-queue',
                Attributes={
                    'VisibilityTimeoutSeconds': '300',
                    'MessageRetentionPeriod': '1209600',
                    'DelaySeconds': '0',
                    'RedrivePolicy': json.dumps({
                        'deadLetterTargetArn': dlq_arn,
                        'maxReceiveCount': 3
                    })
                }
            )
            queue_urls['processing_queue'] = processing_response['QueueUrl']
            
            # Results queue
            results_response = self.sqs_client.create_queue(
                QueueName='clinical-results-queue',
                Attributes={
                    'VisibilityTimeoutSeconds': '60',
                    'MessageRetentionPeriod': '1209600',
                    'DelaySeconds': '0'
                }
            )
            queue_urls['results_queue'] = results_response['QueueUrl']
            
            logger.info("SQS queues created successfully")
            return queue_urls
            
        except Exception as e:
            logger.error(f"Error creating SQS queues: {str(e)}")
            raise
    
    def deploy_lambda_function(self, package_path: str, role_arn: str, queue_urls: Dict[str, str]) -> str:
        """
        Deploy Lambda function
        
        Args:
            package_path: Path to Lambda deployment package
            role_arn: ARN of IAM role
            queue_urls: Dictionary of SQS queue URLs
            
        Returns:
            str: ARN of deployed Lambda function
        """
        try:
            # Read deployment package
            with open(package_path, 'rb') as package_file:
                package_data = package_file.read()
            
            # Environment variables
            environment_vars = {
                'DOCUMENT_BUCKET': 'clinical-documents',
                'PROCESSING_QUEUE_URL': queue_urls.get('processing_queue', ''),
                'RESULTS_QUEUE_URL': queue_urls.get('results_queue', ''),
                'DEAD_LETTER_QUEUE_URL': queue_urls.get('dead_letter_queue', ''),
                'AWS_REGION': self.aws_region,
                'DJANGO_SETTINGS_MODULE': 'RxBackend.settings'
            }
            
            # Create Lambda function
            response = self.lambda_client.create_function(
                FunctionName=self.function_name,
                Runtime='python3.9',
                Role=role_arn,
                Handler='lambda_function.lambda_handler',
                Code={'ZipFile': package_data},
                Description='Clinical document processing Lambda function',
                Timeout=300,  # 5 minutes
                MemorySize=1024,  # 1GB
                Environment={'Variables': environment_vars},
                Tags={
                    'Project': 'RxDoctor',
                    'Component': 'ClinicalRecords',
                    'Environment': 'Production'
                }
            )
            
            function_arn = response['FunctionArn']
            
            # Configure SQS trigger
            self._configure_sqs_trigger(function_arn, queue_urls['processing_queue'])
            
            logger.info(f"Lambda function deployed: {function_arn}")
            return function_arn
            
        except Exception as e:
            logger.error(f"Error deploying Lambda function: {str(e)}")
            raise
    
    def _configure_sqs_trigger(self, function_arn: str, queue_url: str):
        """Configure SQS trigger for Lambda function"""
        try:
            # Get queue ARN
            queue_attrs = self.sqs_client.get_queue_attributes(
                QueueUrl=queue_url,
                AttributeNames=['QueueArn']
            )
            queue_arn = queue_attrs['Attributes']['QueueArn']
            
            # Create event source mapping
            self.lambda_client.create_event_source_mapping(
                EventSourceArn=queue_arn,
                FunctionName=self.function_name,
                BatchSize=10,
                MaximumBatchingWindowInSeconds=5
            )
            
            logger.info(f"SQS trigger configured for {function_arn}")
            
        except Exception as e:
            logger.error(f"Error configuring SQS trigger: {str(e)}")
            raise
    
    def update_lambda_function(self, package_path: str) -> bool:
        """
        Update existing Lambda function
        
        Args:
            package_path: Path to new deployment package
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Read deployment package
            with open(package_path, 'rb') as package_file:
                package_data = package_file.read()
            
            # Update function code
            self.lambda_client.update_function_code(
                FunctionName=self.function_name,
                ZipFile=package_data
            )
            
            logger.info(f"Lambda function {self.function_name} updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error updating Lambda function: {str(e)}")
            return False
    
    def create_cloudformation_template(self) -> Dict[str, Any]:
        """
        Create CloudFormation template for Lambda infrastructure
        
        Returns:
            Dict containing CloudFormation template
        """
        template = {
            "AWSTemplateFormatVersion": "2010-09-09",
            "Description": "Clinical Records Lambda Processing Infrastructure",
            "Parameters": {
                "DocumentBucket": {
                    "Type": "String",
                    "Default": "clinical-documents",
                    "Description": "S3 bucket for clinical documents"
                },
                "Environment": {
                    "Type": "String",
                    "Default": "production",
                    "AllowedValues": ["development", "staging", "production"],
                    "Description": "Environment name"
                }
            },
            "Resources": {
                "ProcessingQueue": {
                    "Type": "AWS::SQS::Queue",
                    "Properties": {
                        "QueueName": {"Fn::Sub": "clinical-processing-queue-${Environment}"},
                        "VisibilityTimeoutSeconds": 300,
                        "MessageRetentionPeriod": 1209600,
                        "RedrivePolicy": {
                            "deadLetterTargetArn": {"Fn::GetAtt": ["DeadLetterQueue", "Arn"]},
                            "maxReceiveCount": 3
                        }
                    }
                },
                "ResultsQueue": {
                    "Type": "AWS::SQS::Queue",
                    "Properties": {
                        "QueueName": {"Fn::Sub": "clinical-results-queue-${Environment}"},
                        "VisibilityTimeoutSeconds": 60,
                        "MessageRetentionPeriod": 1209600
                    }
                },
                "DeadLetterQueue": {
                    "Type": "AWS::SQS::Queue",
                    "Properties": {
                        "QueueName": {"Fn::Sub": "clinical-processing-dlq-${Environment}"},
                        "MessageRetentionPeriod": 1209600
                    }
                },
                "LambdaExecutionRole": {
                    "Type": "AWS::IAM::Role",
                    "Properties": {
                        "RoleName": {"Fn::Sub": "clinical-document-processor-role-${Environment}"},
                        "AssumeRolePolicyDocument": {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Principal": {"Service": "lambda.amazonaws.com"},
                                    "Action": "sts:AssumeRole"
                                }
                            ]
                        },
                        "ManagedPolicyArns": [
                            "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
                        ],
                        "Policies": [
                            {
                                "PolicyName": "ClinicalDocumentProcessingPolicy",
                                "PolicyDocument": {
                                    "Version": "2012-10-17",
                                    "Statement": [
                                        {
                                            "Effect": "Allow",
                                            "Action": [
                                                "s3:GetObject",
                                                "s3:PutObject",
                                                "s3:DeleteObject"
                                            ],
                                            "Resource": [
                                                {"Fn::Sub": "arn:aws:s3:::${DocumentBucket}/*"}
                                            ]
                                        },
                                        {
                                            "Effect": "Allow",
                                            "Action": [
                                                "sqs:ReceiveMessage",
                                                "sqs:DeleteMessage",
                                                "sqs:SendMessage",
                                                "sqs:GetQueueAttributes"
                                            ],
                                            "Resource": [
                                                {"Fn::GetAtt": ["ProcessingQueue", "Arn"]},
                                                {"Fn::GetAtt": ["ResultsQueue", "Arn"]},
                                                {"Fn::GetAtt": ["DeadLetterQueue", "Arn"]}
                                            ]
                                        },
                                        {
                                            "Effect": "Allow",
                                            "Action": [
                                                "textract:DetectDocumentText",
                                                "textract:AnalyzeDocument"
                                            ],
                                            "Resource": "*"
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                },
                "DocumentProcessorFunction": {
                    "Type": "AWS::Lambda::Function",
                    "Properties": {
                        "FunctionName": {"Fn::Sub": "clinical-document-processor-${Environment}"},
                        "Runtime": "python3.9",
                        "Handler": "lambda_function.lambda_handler",
                        "Role": {"Fn::GetAtt": ["LambdaExecutionRole", "Arn"]},
                        "Timeout": 300,
                        "MemorySize": 1024,
                        "Environment": {
                            "Variables": {
                                "DOCUMENT_BUCKET": {"Ref": "DocumentBucket"},
                                "PROCESSING_QUEUE_URL": {"Ref": "ProcessingQueue"},
                                "RESULTS_QUEUE_URL": {"Ref": "ResultsQueue"},
                                "DEAD_LETTER_QUEUE_URL": {"Ref": "DeadLetterQueue"},
                                "ENVIRONMENT": {"Ref": "Environment"}
                            }
                        },
                        "Code": {
                            "ZipFile": "# Placeholder code - replace with actual deployment package\ndef lambda_handler(event, context):\n    return {'statusCode': 200, 'body': 'Hello from Lambda!'}\n"
                        }
                    }
                },
                "SQSEventSourceMapping": {
                    "Type": "AWS::Lambda::EventSourceMapping",
                    "Properties": {
                        "EventSourceArn": {"Fn::GetAtt": ["ProcessingQueue", "Arn"]},
                        "FunctionName": {"Ref": "DocumentProcessorFunction"},
                        "BatchSize": 10,
                        "MaximumBatchingWindowInSeconds": 5
                    }
                }
            },
            "Outputs": {
                "ProcessingQueueUrl": {
                    "Description": "URL of the processing queue",
                    "Value": {"Ref": "ProcessingQueue"},
                    "Export": {"Name": {"Fn::Sub": "${AWS::StackName}-ProcessingQueueUrl"}}
                },
                "ResultsQueueUrl": {
                    "Description": "URL of the results queue",
                    "Value": {"Ref": "ResultsQueue"},
                    "Export": {"Name": {"Fn::Sub": "${AWS::StackName}-ResultsQueueUrl"}}
                },
                "DeadLetterQueueUrl": {
                    "Description": "URL of the dead letter queue",
                    "Value": {"Ref": "DeadLetterQueue"},
                    "Export": {"Name": {"Fn::Sub": "${AWS::StackName}-DeadLetterQueueUrl"}}
                },
                "LambdaFunctionArn": {
                    "Description": "ARN of the Lambda function",
                    "Value": {"Fn::GetAtt": ["DocumentProcessorFunction", "Arn"]},
                    "Export": {"Name": {"Fn::Sub": "${AWS::StackName}-LambdaFunctionArn"}}
                }
            }
        }
        
        return template
    
    def deploy_cloudformation_stack(self, template: Dict[str, Any], parameters: Dict[str, str] = None) -> str:
        """
        Deploy CloudFormation stack
        
        Args:
            template: CloudFormation template
            parameters: Stack parameters
            
        Returns:
            str: Stack ID
        """
        try:
            # Prepare parameters
            cf_parameters = []
            if parameters:
                for key, value in parameters.items():
                    cf_parameters.append({
                        'ParameterKey': key,
                        'ParameterValue': value
                    })
            
            # Create stack
            response = self.cloudformation_client.create_stack(
                StackName=self.stack_name,
                TemplateBody=json.dumps(template),
                Parameters=cf_parameters,
                Capabilities=['CAPABILITY_NAMED_IAM'],
                Tags=[
                    {'Key': 'Project', 'Value': 'RxDoctor'},
                    {'Key': 'Component', 'Value': 'ClinicalRecords'},
                    {'Key': 'ManagedBy', 'Value': 'CloudFormation'}
                ]
            )
            
            stack_id = response['StackId']
            logger.info(f"CloudFormation stack deployment started: {stack_id}")
            
            return stack_id
            
        except Exception as e:
            logger.error(f"Error deploying CloudFormation stack: {str(e)}")
            raise
    
    def wait_for_stack_completion(self, stack_id: str, timeout_minutes: int = 30) -> bool:
        """
        Wait for CloudFormation stack to complete
        
        Args:
            stack_id: Stack ID to wait for
            timeout_minutes: Maximum time to wait
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            waiter = self.cloudformation_client.get_waiter('stack_create_complete')
            waiter.wait(
                StackName=stack_id,
                WaiterConfig={
                    'Delay': 30,
                    'MaxAttempts': timeout_minutes * 2
                }
            )
            
            logger.info(f"CloudFormation stack completed successfully: {stack_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error waiting for stack completion: {str(e)}")
            return False
    
    def get_stack_outputs(self, stack_name: str = None) -> Dict[str, str]:
        """
        Get CloudFormation stack outputs
        
        Args:
            stack_name: Name of the stack (defaults to self.stack_name)
            
        Returns:
            Dict containing stack outputs
        """
        try:
            if not stack_name:
                stack_name = self.stack_name
            
            response = self.cloudformation_client.describe_stacks(
                StackName=stack_name
            )
            
            outputs = {}
            for stack in response['Stacks']:
                for output in stack.get('Outputs', []):
                    outputs[output['OutputKey']] = output['OutputValue']
            
            return outputs
            
        except Exception as e:
            logger.error(f"Error getting stack outputs: {str(e)}")
            return {}
    
    def full_deployment(self, source_dir: str, environment: str = 'production') -> Dict[str, Any]:
        """
        Perform full deployment of Lambda infrastructure
        
        Args:
            source_dir: Directory containing Lambda source code
            environment: Environment name
            
        Returns:
            Dict containing deployment results
        """
        try:
            deployment_results = {
                'timestamp': datetime.now().isoformat(),
                'environment': environment,
                'success': False,
                'components': {}
            }
            
            # Create deployment package
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
                package_path = temp_file.name
            
            self.create_lambda_package(source_dir, package_path)
            deployment_results['components']['package'] = {'status': 'created', 'path': package_path}
            
            # Create CloudFormation template
            template = self.create_cloudformation_template()
            
            # Deploy CloudFormation stack
            parameters = {
                'Environment': environment,
                'DocumentBucket': f'clinical-documents-{environment}'
            }
            
            stack_id = self.deploy_cloudformation_stack(template, parameters)
            deployment_results['components']['cloudformation'] = {'status': 'deploying', 'stack_id': stack_id}
            
            # Wait for stack completion
            if self.wait_for_stack_completion(stack_id):
                deployment_results['components']['cloudformation']['status'] = 'completed'
                
                # Get stack outputs
                outputs = self.get_stack_outputs()
                deployment_results['components']['outputs'] = outputs
                
                # Update Lambda function code
                function_name = f"clinical-document-processor-{environment}"
                
                # Read and update function code
                with open(package_path, 'rb') as package_file:
                    package_data = package_file.read()
                
                self.lambda_client.update_function_code(
                    FunctionName=function_name,
                    ZipFile=package_data
                )
                
                deployment_results['components']['lambda_update'] = {'status': 'completed'}
                deployment_results['success'] = True
            else:
                deployment_results['components']['cloudformation']['status'] = 'failed'
            
            # Cleanup
            os.unlink(package_path)
            
            return deployment_results
            
        except Exception as e:
            logger.error(f"Error in full deployment: {str(e)}")
            deployment_results['error'] = str(e)
            return deployment_results