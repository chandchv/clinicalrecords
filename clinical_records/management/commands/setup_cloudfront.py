#!/usr/bin/env python3
"""
Management command for setting up CloudFront CDN for clinical records S3 bucket.
Handles CloudFront distribution creation and configuration.
"""

import json
import logging
import time
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from clinical_records.config.s3_config import get_s3_config
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Set up CloudFront CDN for clinical records S3 bucket'

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            type=str,
            choices=[
                'create',
                'update',
                'status',
                'invalidate',
                'delete'
            ],
            help='Action to perform'
        )
        parser.add_argument(
            '--distribution-id',
            type=str,
            help='CloudFront distribution ID (for update/status/invalidate/delete)'
        )
        parser.add_argument(
            '--origin-access-identity',
            type=str,
            help='CloudFront Origin Access Identity ID'
        )
        parser.add_argument(
            '--price-class',
            type=str,
            choices=['PriceClass_All', 'PriceClass_100', 'PriceClass_200'],
            default='PriceClass_100',
            help='CloudFront price class'
        )
        parser.add_argument(
            '--cache-behavior',
            type=str,
            choices=['default', 'secure', 'no-cache'],
            default='secure',
            help='Cache behavior configuration'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Perform dry run without making changes'
        )
        parser.add_argument(
            '--wait',
            action='store_true',
            help='Wait for distribution deployment to complete'
        )

    def handle(self, *args, **options):
        """Main command execution"""
        try:
            self.action = options['action']
            self.distribution_id = options.get('distribution_id')
            self.origin_access_identity = options.get('origin_access_identity')
            self.price_class = options['price_class']
            self.cache_behavior = options['cache_behavior']
            self.dry_run = options['dry_run']
            self.wait = options['wait']
            
            # Get S3 configuration
            self.s3_config = get_s3_config()
            
            # Initialize CloudFront client
            self.cloudfront_client = boto3.client('cloudfront')
            
            self.stdout.write(f"Starting CloudFront action: {self.action}")
            
            # Execute action
            if self.action == 'create':
                self.create_distribution()
            elif self.action == 'update':
                self.update_distribution()
            elif self.action == 'status':
                self.show_distribution_status()
            elif self.action == 'invalidate':
                self.create_invalidation()
            elif self.action == 'delete':
                self.delete_distribution()
            
            self.stdout.write(
                self.style.SUCCESS(f'CloudFront action completed: {self.action}')
            )
            
        except Exception as e:
            logger.error(f"CloudFront command failed: {e}")
            raise CommandError(f'CloudFront command failed: {e}')

    def create_distribution(self):
        """Create CloudFront distribution"""
        self.stdout.write("Creating CloudFront distribution...")
        
        # Create Origin Access Identity if not provided
        if not self.origin_access_identity:
            oai_id = self.create_origin_access_identity()
        else:
            oai_id = self.origin_access_identity
        
        # Distribution configuration
        distribution_config = self.get_distribution_config(oai_id)
        
        if self.dry_run:
            self.stdout.write("Would create CloudFront distribution with config:")
            self.stdout.write(json.dumps(distribution_config, indent=2, default=str))
            return
        
        try:
            response = self.cloudfront_client.create_distribution(
                DistributionConfig=distribution_config
            )
            
            distribution = response['Distribution']
            distribution_id = distribution['Id']
            domain_name = distribution['DomainName']
            
            self.stdout.write(f"✅ Created CloudFront distribution:")
            self.stdout.write(f"  Distribution ID: {distribution_id}")
            self.stdout.write(f"  Domain Name: {domain_name}")
            self.stdout.write(f"  Status: {distribution['Status']}")
            
            # Update S3 bucket policy to allow CloudFront access
            self.update_s3_bucket_policy(oai_id)
            
            if self.wait:
                self.wait_for_deployment(distribution_id)
            
        except ClientError as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to create distribution: {e}"))
            raise

    def create_origin_access_identity(self):
        """Create CloudFront Origin Access Identity"""
        self.stdout.write("Creating Origin Access Identity...")
        
        oai_config = {
            'CallerReference': f"clinical-records-{int(time.time())}",
            'Comment': f'OAI for clinical records bucket {self.s3_config.BUCKET_NAME}'
        }
        
        if self.dry_run:
            self.stdout.write("Would create Origin Access Identity")
            return "dummy-oai-id"
        
        try:
            response = self.cloudfront_client.create_cloud_front_origin_access_identity(
                CloudFrontOriginAccessIdentityConfig=oai_config
            )
            
            oai = response['CloudFrontOriginAccessIdentity']
            oai_id = oai['Id']
            
            self.stdout.write(f"✅ Created Origin Access Identity: {oai_id}")
            return oai_id
            
        except ClientError as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to create OAI: {e}"))
            raise

    def get_distribution_config(self, oai_id):
        """Get CloudFront distribution configuration"""
        cache_behaviors = self.get_cache_behaviors()
        
        config = {
            'CallerReference': f"clinical-records-{int(time.time())}",
            'Comment': f'CloudFront distribution for clinical records bucket {self.s3_config.BUCKET_NAME}',
            'DefaultRootObject': '',
            'Origins': {
                'Quantity': 1,
                'Items': [
                    {
                        'Id': f'{self.s3_config.BUCKET_NAME}-origin',
                        'DomainName': f'{self.s3_config.BUCKET_NAME}.s3.{self.s3_config.REGION_NAME}.amazonaws.com',
                        'S3OriginConfig': {
                            'OriginAccessIdentity': f'origin-access-identity/cloudfront/{oai_id}'
                        }
                    }
                ]
            },
            'DefaultCacheBehavior': cache_behaviors['default'],
            'CacheBehaviors': {
                'Quantity': len(cache_behaviors.get('additional', [])),
                'Items': cache_behaviors.get('additional', [])
            },
            'Enabled': True,
            'PriceClass': self.price_class,
            'ViewerCertificate': {
                'CloudFrontDefaultCertificate': True
            },
            'WebACLId': '',
            'HttpVersion': 'http2',
            'IsIPV6Enabled': True,
            'Restrictions': {
                'GeoRestriction': {
                    'RestrictionType': 'none'
                }
            },
            'Logging': {
                'Enabled': True,
                'IncludeCookies': False,
                'Bucket': f'{self.s3_config.BUCKET_NAME}.s3.amazonaws.com',
                'Prefix': 'cloudfront-logs/'
            }
        }
        
        return config

    def get_cache_behaviors(self):
        """Get cache behavior configurations"""
        if self.cache_behavior == 'secure':
            default_behavior = {
                'TargetOriginId': f'{self.s3_config.BUCKET_NAME}-origin',
                'ViewerProtocolPolicy': 'redirect-to-https',
                'TrustedSigners': {
                    'Enabled': True,
                    'Quantity': 1,
                    'Items': ['self']
                },
                'ForwardedValues': {
                    'QueryString': True,
                    'Cookies': {'Forward': 'none'},
                    'Headers': {
                        'Quantity': 3,
                        'Items': ['Authorization', 'Date', 'Host']
                    }
                },
                'MinTTL': 0,
                'DefaultTTL': 300,  # 5 minutes
                'MaxTTL': 3600,     # 1 hour
                'Compress': True,
                'AllowedMethods': {
                    'Quantity': 7,
                    'Items': ['GET', 'HEAD', 'OPTIONS', 'PUT', 'POST', 'PATCH', 'DELETE'],
                    'CachedMethods': {
                        'Quantity': 2,
                        'Items': ['GET', 'HEAD']
                    }
                }
            }
        elif self.cache_behavior == 'no-cache':
            default_behavior = {
                'TargetOriginId': f'{self.s3_config.BUCKET_NAME}-origin',
                'ViewerProtocolPolicy': 'redirect-to-https',
                'TrustedSigners': {
                    'Enabled': False,
                    'Quantity': 0
                },
                'ForwardedValues': {
                    'QueryString': True,
                    'Cookies': {'Forward': 'all'},
                    'Headers': {
                        'Quantity': 1,
                        'Items': ['*']
                    }
                },
                'MinTTL': 0,
                'DefaultTTL': 0,
                'MaxTTL': 0,
                'Compress': False,
                'AllowedMethods': {
                    'Quantity': 7,
                    'Items': ['GET', 'HEAD', 'OPTIONS', 'PUT', 'POST', 'PATCH', 'DELETE'],
                    'CachedMethods': {
                        'Quantity': 2,
                        'Items': ['GET', 'HEAD']
                    }
                }
            }
        else:  # default
            default_behavior = {
                'TargetOriginId': f'{self.s3_config.BUCKET_NAME}-origin',
                'ViewerProtocolPolicy': 'redirect-to-https',
                'TrustedSigners': {
                    'Enabled': False,
                    'Quantity': 0
                },
                'ForwardedValues': {
                    'QueryString': False,
                    'Cookies': {'Forward': 'none'}
                },
                'MinTTL': 0,
                'DefaultTTL': 86400,  # 24 hours
                'MaxTTL': 31536000,   # 1 year
                'Compress': True,
                'AllowedMethods': {
                    'Quantity': 2,
                    'Items': ['GET', 'HEAD'],
                    'CachedMethods': {
                        'Quantity': 2,
                        'Items': ['GET', 'HEAD']
                    }
                }
            }
        
        return {
            'default': default_behavior,
            'additional': []
        }

    def update_s3_bucket_policy(self, oai_id):
        """Update S3 bucket policy to allow CloudFront access"""
        self.stdout.write("Updating S3 bucket policy for CloudFront access...")
        
        if self.dry_run:
            self.stdout.write("Would update S3 bucket policy")
            return
        
        try:
            s3_client = boto3.client('s3')
            
            # Get existing bucket policy
            try:
                response = s3_client.get_bucket_policy(Bucket=self.s3_config.BUCKET_NAME)
                policy = json.loads(response['Policy'])
            except ClientError as e:
                if e.response['Error']['Code'] == 'NoSuchBucketPolicy':
                    policy = {
                        "Version": "2012-10-17",
                        "Statement": []
                    }
                else:
                    raise
            
            # Add CloudFront access statement
            cloudfront_statement = {
                "Sid": "AllowCloudFrontAccess",
                "Effect": "Allow",
                "Principal": {
                    "AWS": f"arn:aws:iam::cloudfront:user/CloudFront Origin Access Identity {oai_id}"
                },
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{self.s3_config.BUCKET_NAME}/*"
            }
            
            # Check if statement already exists
            existing_statement = None
            for i, statement in enumerate(policy['Statement']):
                if statement.get('Sid') == 'AllowCloudFrontAccess':
                    existing_statement = i
                    break
            
            if existing_statement is not None:
                policy['Statement'][existing_statement] = cloudfront_statement
            else:
                policy['Statement'].append(cloudfront_statement)
            
            # Update bucket policy
            s3_client.put_bucket_policy(
                Bucket=self.s3_config.BUCKET_NAME,
                Policy=json.dumps(policy)
            )
            
            self.stdout.write("✅ Updated S3 bucket policy for CloudFront access")
            
        except ClientError as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to update S3 bucket policy: {e}"))
            raise

    def update_distribution(self):
        """Update existing CloudFront distribution"""
        if not self.distribution_id:
            raise CommandError("Distribution ID is required for update action")
        
        self.stdout.write(f"Updating CloudFront distribution {self.distribution_id}...")
        
        if self.dry_run:
            self.stdout.write("Would update CloudFront distribution")
            return
        
        try:
            # Get current distribution config
            response = self.cloudfront_client.get_distribution_config(
                Id=self.distribution_id
            )
            
            config = response['DistributionConfig']
            etag = response['ETag']
            
            # Update configuration as needed
            # (Add specific updates here based on requirements)
            
            # Update distribution
            self.cloudfront_client.update_distribution(
                Id=self.distribution_id,
                DistributionConfig=config,
                IfMatch=etag
            )
            
            self.stdout.write(f"✅ Updated CloudFront distribution {self.distribution_id}")
            
            if self.wait:
                self.wait_for_deployment(self.distribution_id)
            
        except ClientError as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to update distribution: {e}"))
            raise

    def show_distribution_status(self):
        """Show CloudFront distribution status"""
        if not self.distribution_id:
            raise CommandError("Distribution ID is required for status action")
        
        try:
            response = self.cloudfront_client.get_distribution(
                Id=self.distribution_id
            )
            
            distribution = response['Distribution']
            
            self.stdout.write(f"\nCloudFront Distribution Status:")
            self.stdout.write(f"  ID: {distribution['Id']}")
            self.stdout.write(f"  Domain Name: {distribution['DomainName']}")
            self.stdout.write(f"  Status: {distribution['Status']}")
            self.stdout.write(f"  Enabled: {distribution['DistributionConfig']['Enabled']}")
            self.stdout.write(f"  Price Class: {distribution['DistributionConfig']['PriceClass']}")
            self.stdout.write(f"  Last Modified: {distribution['LastModifiedTime']}")
            
            # Show origins
            origins = distribution['DistributionConfig']['Origins']['Items']
            self.stdout.write(f"  Origins:")
            for origin in origins:
                self.stdout.write(f"    - {origin['Id']}: {origin['DomainName']}")
            
        except ClientError as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to get distribution status: {e}"))
            raise

    def create_invalidation(self):
        """Create CloudFront cache invalidation"""
        if not self.distribution_id:
            raise CommandError("Distribution ID is required for invalidation action")
        
        self.stdout.write(f"Creating cache invalidation for distribution {self.distribution_id}...")
        
        if self.dry_run:
            self.stdout.write("Would create cache invalidation")
            return
        
        try:
            invalidation_config = {
                'Paths': {
                    'Quantity': 1,
                    'Items': ['/*']  # Invalidate all paths
                },
                'CallerReference': f"invalidation-{int(time.time())}"
            }
            
            response = self.cloudfront_client.create_invalidation(
                DistributionId=self.distribution_id,
                InvalidationBatch=invalidation_config
            )
            
            invalidation = response['Invalidation']
            
            self.stdout.write(f"✅ Created cache invalidation:")
            self.stdout.write(f"  Invalidation ID: {invalidation['Id']}")
            self.stdout.write(f"  Status: {invalidation['Status']}")
            self.stdout.write(f"  Create Time: {invalidation['CreateTime']}")
            
        except ClientError as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to create invalidation: {e}"))
            raise

    def delete_distribution(self):
        """Delete CloudFront distribution"""
        if not self.distribution_id:
            raise CommandError("Distribution ID is required for delete action")
        
        self.stdout.write(f"Deleting CloudFront distribution {self.distribution_id}...")
        
        if self.dry_run:
            self.stdout.write("Would delete CloudFront distribution")
            return
        
        try:
            # First disable the distribution
            response = self.cloudfront_client.get_distribution_config(
                Id=self.distribution_id
            )
            
            config = response['DistributionConfig']
            etag = response['ETag']
            
            if config['Enabled']:
                self.stdout.write("Disabling distribution before deletion...")
                config['Enabled'] = False
                
                self.cloudfront_client.update_distribution(
                    Id=self.distribution_id,
                    DistributionConfig=config,
                    IfMatch=etag
                )
                
                # Wait for distribution to be disabled
                self.wait_for_deployment(self.distribution_id)
                
                # Get new ETag after update
                response = self.cloudfront_client.get_distribution_config(
                    Id=self.distribution_id
                )
                etag = response['ETag']
            
            # Delete the distribution
            self.cloudfront_client.delete_distribution(
                Id=self.distribution_id,
                IfMatch=etag
            )
            
            self.stdout.write(f"✅ Deleted CloudFront distribution {self.distribution_id}")
            
        except ClientError as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to delete distribution: {e}"))
            raise

    def wait_for_deployment(self, distribution_id):
        """Wait for CloudFront distribution deployment to complete"""
        self.stdout.write("Waiting for distribution deployment to complete...")
        
        max_wait_time = 1800  # 30 minutes
        check_interval = 30   # 30 seconds
        elapsed_time = 0
        
        while elapsed_time < max_wait_time:
            try:
                response = self.cloudfront_client.get_distribution(
                    Id=distribution_id
                )
                
                status = response['Distribution']['Status']
                
                if status == 'Deployed':
                    self.stdout.write("✅ Distribution deployment completed")
                    return
                
                self.stdout.write(f"Distribution status: {status} (waiting...)")
                time.sleep(check_interval)
                elapsed_time += check_interval
                
            except ClientError as e:
                self.stdout.write(self.style.ERROR(f"❌ Error checking deployment status: {e}"))
                break
        
        self.stdout.write(self.style.WARNING("⚠️  Deployment wait timeout reached"))