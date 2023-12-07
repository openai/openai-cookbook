# Remove once this PR is merged: https://github.com/openai/openai-python/pull/590 and openai release is made
!pip uninstall -y openai -qq \
&& pip install git+https://github.com/morganmcg1/openai-python.git@update_wandb_logger -qqq