for step in run_steps.data:
    step_details = step.step_details
    print(json.dumps(show_json(step_details), indent=4))