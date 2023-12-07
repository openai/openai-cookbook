thread, run = create_thread_and_run(
    "What are some cool math concepts behind this ML paper pdf? Explain in two sentences."
)
run = wait_on_run(run, thread)
pretty_print(get_response(thread))