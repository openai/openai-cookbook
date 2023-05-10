# running pytest using the docker

WORKSPACE_LOCATION=/test_code
# "pip install --upgrade pip" -c "pip install -r glue_requirements.txt "  -c "python3 -m run tests/ --abc=hi --env_file_path=hihi --cfg_file_path=hihihi"
docker run -it -v ~/.aws:/home/glue_user/.aws -v $WORKSPACE_LOCATION:/home/glue_user/workspace/ -e AWS_PROFILE=$PROFILE_NAME -e DISABLE_SSL=true --rm -p 4040:4040 -p 18080:18080 --name glue_pytest amazon/aws-glue-libs:glue_libs_3.0.0_image_01 -c "python3 -m pytest"