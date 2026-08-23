"""CloudFormation template used by the prior authorization example."""

from copy import deepcopy


KB_TEMPLATE = {
    "AWSTemplateFormatVersion": "2010-09-09",
    "Description": (
        "Bedrock Managed Knowledge Base for public CMS policy retrieval."
    ),
    "Parameters": {
        "ResourcePrefix": {
            "Type": "String",
            "Default": "policy-to-review-cms",
            "AllowedPattern": "^[a-z][a-z0-9-]{2,23}$",
        },
        "KnowledgeBaseRoleArn": {
            "Type": "String",
            "Default": "",
            "AllowedPattern": (
                "^$|^arn:aws(-[a-z]+)?:iam::[0-9]{12}:role/.+$"
            ),
        },
        "KnowledgeBaseRolePath": {
            "Type": "String",
            "Default": "/",
            "AllowedPattern": (
                "^/$|^/[A-Za-z0-9+=,.@_-]+(?:/"
                "[A-Za-z0-9+=,.@_-]+)*/$"
            ),
        },
        "KnowledgeBasePermissionsBoundaryArn": {
            "Type": "String",
            "Default": "",
            "AllowedPattern": (
                "^$|^arn:aws(-[a-z]+)?:iam::[0-9]{12}:policy/.+$"
            ),
        },
    },
    "Conditions": {
        "CreateKnowledgeBaseRole": {
            "Fn::Equals": [{"Ref": "KnowledgeBaseRoleArn"}, ""]
        },
        "UseKnowledgeBasePermissionsBoundary": {
            "Fn::Not": [{"Fn::Equals": [
                {"Ref": "KnowledgeBasePermissionsBoundaryArn"},
                "",
            ]}]
        },
    },
    "Resources": {
        "PolicySourceBucket": {
            "Type": "AWS::S3::Bucket",
            "Properties": {
                "BucketName": {
                    "Fn::Sub": (
                        "${ResourcePrefix}-${AWS::AccountId}-"
                        "${AWS::Region}-mkb-src"
                    )
                },
                "BucketEncryption": {
                    "ServerSideEncryptionConfiguration": [
                        {
                            "ServerSideEncryptionByDefault": {
                                "SSEAlgorithm": "AES256"
                            }
                        }
                    ]
                },
                "OwnershipControls": {
                    "Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]
                },
                "PublicAccessBlockConfiguration": {
                    "BlockPublicAcls": True,
                    "BlockPublicPolicy": True,
                    "IgnorePublicAcls": True,
                    "RestrictPublicBuckets": True,
                },
                "VersioningConfiguration": {"Status": "Enabled"},
                "Tags": [
                    {
                        "Key": "example",
                        "Value": "policy-to-review",
                    },
                    {
                        "Key": "data-classification",
                        "Value": "public-official",
                    },
                    {
                        "Key": "retrieval",
                        "Value": "managed-hybrid",
                    },
                ],
            },
        },
        "KnowledgeBaseRole": {
            "Type": "AWS::IAM::Role",
            "Condition": "CreateKnowledgeBaseRole",
            "Properties": {
                "Path": {"Ref": "KnowledgeBaseRolePath"},
                "PermissionsBoundary": {
                    "Fn::If": [
                        "UseKnowledgeBasePermissionsBoundary",
                        {
                            "Ref": (
                                "KnowledgeBasePermissionsBoundaryArn"
                            )
                        },
                        {"Ref": "AWS::NoValue"},
                    ]
                },
                "Description": (
                    "Service role for the public CMS Managed Knowledge Base."
                ),
                "AssumeRolePolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {
                                "Service": "bedrock.amazonaws.com"
                            },
                            "Action": "sts:AssumeRole",
                            "Condition": {
                                "StringEquals": {
                                    "aws:SourceAccount": {
                                        "Ref": "AWS::AccountId"
                                    }
                                },
                                "ArnLike": {
                                    "AWS:SourceArn": {
                                        "Fn::Sub": (
                                            "arn:${AWS::Partition}:bedrock:"
                                            "${AWS::Region}:"
                                            "${AWS::AccountId}:"
                                            "knowledge-base/*"
                                        )
                                    }
                                },
                            },
                        }
                    ],
                },
                "Policies": [
                    {
                        "PolicyName": "ReadPublicPolicySource",
                        "PolicyDocument": {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Action": "s3:ListBucket",
                                    "Resource": {
                                        "Fn::GetAtt": [
                                            "PolicySourceBucket",
                                            "Arn",
                                        ]
                                    },
                                    "Condition": {
                                        "StringLike": {
                                            "s3:prefix": [
                                                "policies/public/cms/*"
                                            ]
                                        },
                                        "StringEquals": {
                                            "aws:ResourceAccount": {
                                                "Ref": "AWS::AccountId"
                                            }
                                        },
                                    },
                                },
                                {
                                    "Effect": "Allow",
                                    "Action": "s3:GetObject",
                                    "Resource": {
                                        "Fn::Sub": (
                                            "${PolicySourceBucket.Arn}/"
                                            "policies/public/cms/*"
                                        )
                                    },
                                    "Condition": {
                                        "StringEquals": {
                                            "aws:ResourceAccount": {
                                                "Ref": "AWS::AccountId"
                                            }
                                        }
                                    },
                                },
                            ],
                        },
                    },
                ],
            },
        },
        "PolicyKnowledgeBase": {
            "Type": "AWS::Bedrock::KnowledgeBase",
            "Properties": {
                "Name": {"Fn::Sub": "${ResourcePrefix}-managed-kb"},
                "Description": (
                    "Managed hybrid retrieval over approved public CMS policy "
                    "snapshots for prior authorization review."
                ),
                "RoleArn": {
                    "Fn::If": [
                        "CreateKnowledgeBaseRole",
                        {
                            "Fn::GetAtt": [
                                "KnowledgeBaseRole",
                                "Arn",
                            ]
                        },
                        {"Ref": "KnowledgeBaseRoleArn"},
                    ]
                },
                "KnowledgeBaseConfiguration": {
                    "Type": "MANAGED",
                    "ManagedKnowledgeBaseConfiguration": {
                        "EmbeddingModelType": "MANAGED",
                    },
                },
                "Tags": {
                    "example": "policy-to-review",
                    "data-classification": "public-official",
                    "retrieval": "managed-hybrid",
                },
            },
        },
        "PolicyDataSource": {
            "Type": "AWS::Bedrock::DataSource",
            "Properties": {
                "KnowledgeBaseId": {
                    "Ref": "PolicyKnowledgeBase"
                },
                "Name": {"Fn::Sub": "${ResourcePrefix}-cms-policies"},
                "Description": (
                    "Official public CMS policy snapshots with provenance "
                    "and applicability metadata."
                ),
                "DataDeletionPolicy": "DELETE",
                "DataSourceConfiguration": {
                    "Type": "MANAGED_KNOWLEDGE_BASE_CONNECTOR",
                    "ManagedKnowledgeBaseConnectorConfiguration": {
                        "DeletionProtectionConfiguration": {
                            "DeletionProtectionStatus": "ENABLED",
                            "DeletionProtectionThreshold": 10,
                        },
                        "ConnectorParameters": {
                            "type": "S3",
                            "version": "1",
                            "aclEnabled": False,
                            "connectionConfiguration": {
                                "bucketName": {
                                    "Ref": "PolicySourceBucket"
                                },
                                "bucketOwnerAccountId": {
                                    "Ref": "AWS::AccountId"
                                },
                            },
                            "filterConfiguration": {
                                "inclusionPrefixes": [
                                    "policies/public/cms/"
                                ],
                                "maxFileSizeInMegaBytes": "10",
                            },
                        },
                    },
                },
            },
        },
    },
    "Outputs": {
        "KnowledgeBaseId": {
            "Value": {"Ref": "PolicyKnowledgeBase"}
        },
        "DataSourceId": {
            "Value": {
                "Fn::GetAtt": [
                    "PolicyDataSource",
                    "DataSourceId",
                ]
            }
        },
        "PolicySourceBucketName": {
            "Value": {"Ref": "PolicySourceBucket"}
        },
    },
}


def build_knowledge_base_template() -> dict[str, object]:
    """Return an isolated copy that callers can safely modify."""
    return deepcopy(KB_TEMPLATE)
