"""CloudFormation template used by the prior authorization example."""

from copy import deepcopy


KB_TEMPLATE = {
    "AWSTemplateFormatVersion": "2010-09-09",
    "Description": (
        "Public CMS policy Knowledge Base for the prior authorization example."
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
                        "${AWS::Region}-source"
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
                ],
            },
        },
        "PolicyVectorBucket": {
            "Type": "AWS::S3Vectors::VectorBucket",
            "Properties": {
                "VectorBucketName": {
                    "Fn::Sub": (
                        "${ResourcePrefix}-${AWS::AccountId}-"
                        "${AWS::Region}-vectors"
                    )
                },
                "EncryptionConfiguration": {"SseType": "AES256"},
                "Tags": [
                    {
                        "Key": "example",
                        "Value": "policy-to-review",
                    }
                ],
            },
        },
        "PolicyVectorIndex": {
            "Type": "AWS::S3Vectors::Index",
            "Properties": {
                "VectorBucketArn": {"Ref": "PolicyVectorBucket"},
                "IndexName": "public-policy-index",
                "DataType": "float32",
                "Dimension": 1024,
                "DistanceMetric": "cosine",
                "MetadataConfiguration": {
                    "NonFilterableMetadataKeys": [
                        "AMAZON_BEDROCK_TEXT",
                        "AMAZON_BEDROCK_METADATA",
                    ]
                },
                "Tags": [
                    {
                        "Key": "example",
                        "Value": "policy-to-review",
                    }
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
                    "Service role for the public CMS policy Knowledge Base."
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
                        "PolicyName": "InvokeTitanEmbeddingsV2",
                        "PolicyDocument": {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Action": "bedrock:InvokeModel",
                                    "Resource": {
                                        "Fn::Sub": (
                                            "arn:${AWS::Partition}:bedrock:"
                                            "${AWS::Region}::foundation-model/"
                                            "amazon.titan-embed-text-v2:0"
                                        )
                                    },
                                }
                            ],
                        },
                    },
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
                                },
                            ],
                        },
                    },
                    {
                        "PolicyName": "ReadWritePolicyVectors",
                        "PolicyDocument": {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Action": [
                                        "s3vectors:PutVectors",
                                        "s3vectors:GetVectors",
                                        "s3vectors:DeleteVectors",
                                        "s3vectors:QueryVectors",
                                        "s3vectors:GetIndex",
                                    ],
                                    "Resource": {
                                        "Ref": "PolicyVectorIndex"
                                    },
                                }
                            ],
                        },
                    },
                ],
            },
        },
        "PolicyKnowledgeBase": {
            "Type": "AWS::Bedrock::KnowledgeBase",
            "Properties": {
                "Name": {"Fn::Sub": "${ResourcePrefix}-kb"},
                "Description": (
                    "Official CMS policy retrieval for prior authorization review."
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
                    "Type": "VECTOR",
                    "VectorKnowledgeBaseConfiguration": {
                        "EmbeddingModelArn": {
                            "Fn::Sub": (
                                "arn:${AWS::Partition}:bedrock:"
                                "${AWS::Region}::foundation-model/"
                                "amazon.titan-embed-text-v2:0"
                            )
                        },
                        "EmbeddingModelConfiguration": {
                            "BedrockEmbeddingModelConfiguration": {
                                "Dimensions": 1024,
                                "EmbeddingDataType": "FLOAT32",
                            }
                        },
                    },
                },
                "StorageConfiguration": {
                    "Type": "S3_VECTORS",
                    "S3VectorsConfiguration": {
                        "VectorBucketArn": {
                            "Ref": "PolicyVectorBucket"
                        },
                        "IndexArn": {"Ref": "PolicyVectorIndex"},
                    },
                },
            },
        },
        "PolicyDataSource": {
            "Type": "AWS::Bedrock::DataSource",
            "Properties": {
                "KnowledgeBaseId": {
                    "Ref": "PolicyKnowledgeBase"
                },
                "Name": {"Fn::Sub": "${ResourcePrefix}-policies"},
                "DataDeletionPolicy": "DELETE",
                "DataSourceConfiguration": {
                    "Type": "S3",
                    "S3Configuration": {
                        "BucketArn": {
                            "Fn::GetAtt": [
                                "PolicySourceBucket",
                                "Arn",
                            ]
                        },
                        "BucketOwnerAccountId": {
                            "Ref": "AWS::AccountId"
                        },
                        "InclusionPrefixes": [
                            "policies/public/cms/"
                        ],
                    },
                },
                "VectorIngestionConfiguration": {
                    "ChunkingConfiguration": {
                        "ChunkingStrategy": "FIXED_SIZE",
                        "FixedSizeChunkingConfiguration": {
                            "MaxTokens": 400,
                            "OverlapPercentage": 15,
                        },
                    }
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
        "VectorBucketArn": {
            "Value": {"Ref": "PolicyVectorBucket"}
        },
        "VectorIndexArn": {
            "Value": {"Ref": "PolicyVectorIndex"}
        },
    },
}


def build_knowledge_base_template() -> dict[str, object]:
    """Return an isolated copy that callers can safely modify."""
    return deepcopy(KB_TEMPLATE)
