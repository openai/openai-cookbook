# Code explanation examples

GPT's understanding of code can be applied to many use cases, e.g.:

* Generating in-code documentation (e.g., Python docstrings, git commit messages)
* Generating out-of-code documentation (e.g., man pages)
* An interactive code exploration tool
* Communicating program results back to users via a natural language interface

For example, if you wanted to understand a SQL query, you could give `code-davinci-002` the following example prompt:

````text
A SQL query:
```
SELECT c.customer_id
FROM Customers c
JOIN Streaming s
ON c.customer_id = s.customer_id
WHERE c.signup_date BETWEEN '2020-03-01' AND '2020-03-31'
AND s.watch_date BETWEEN c.signup_date AND DATE_ADD(c.signup_date, INTERVAL 30 DAY)
GROUP BY c.customer_id
HAVING SUM(s.watch_minutes) > 50 * 60
```

Questions:
1. What does the SQL query do?
2. Why might someone be interested in this time period?
3. Why might a company be interested in this SQL query?

Answers:
````

[Output]((https://beta.openai.com/playground/p/Sv1VQKbJV1TZKmiTK9r6nlj3)):

```text
1. The SQL query finds all customers who signed up in March 2020 and watched more than 50 hours of content in the first 30 days after signing up.
2. The time period is interesting because it is the first month of the COVID-19 pandemic.
3. A company might be interested in this SQL query because it can help them understand how the pandemic has affected their business.
```

Note that `code-davinci-002` is not trained to follow instructions and therefore usually needs examples or other structure to help steer its output, as well as stop sequences to stop generating. For easier prompting, try `text-davinci-003`.