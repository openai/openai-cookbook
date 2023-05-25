HOST_DIRECTORY=test_code/data_quality_package
CONTAINER_DIRECTORY=/home/glue_user/workspace
PROFILE_NAME=default
sudo cp -r ~/.aws .
sudo chmod -R 777 .
sudo chmod -R 777 .aws
docker run -it \
    -v $(pwd)/.aws:/home/glue_user/.aws \
    -v $(pwd)/$HOST_DIRECTORY:$CONTAINER_DIRECTORY \
    -e AWS_PROFILE=$PROFILE_NAME \
    -e DISABLE_SSL=true \
    --rm -p 4041:4041 -p 18080:18080 \
    --name glue_pytest amazon/aws-glue-libs:glue_libs_3.0.0_image_01 \
    -c "python3 -m pytest --tb=line -rw $1"
