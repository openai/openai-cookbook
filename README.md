# ChatToolbox
## Demo
- Install the requirements_dev packages.
- Provide the `OPENAI_API_KEY` in a `.env` file. 
- Go to test_code (or any other directory of your choice).
- change the `code_toolbox_config.yaml` accordingly.
- if `document: true` you can use sphinx documentation. go to `test_code` directory and use make docs `doc_type=html`. to get a html documentation based on the code in the `test_code/docs/build`. For more information about Sphinx please read the Sphinx documentation.
- if `test: true` you will find the tests in `test_path` folder.
- Code conversion is still under development but you can use `conversion:true` to see scala output in `scala` folder in `test_code` directory.
