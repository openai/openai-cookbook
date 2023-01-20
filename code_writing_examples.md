# Code writing examples

GPT-3 is able to write code as well as text.

Here's an example of `code-davinci-002` writing a SQL query:

````text
SQL tables (and columns):
* Customers(customer_id, signup_date)
* Streaming(customer_id, video_id, watch_date, watch_minutes)

A well-written SQL query that lists customers who signed up during March 2020 and watched more than 50 hours of video in their first 30 days:
```
````

[Output](https://beta.openai.com/playground/p/r2mw99cANoa0TJHok725CeaC):

```sql
SELECT c.customer_id
FROM Customers c
JOIN Streaming s
ON c.customer_id = s.customer_id
WHERE c.signup_date BETWEEN '2020-03-01' AND '2020-03-31'
AND s.watch_date BETWEEN c.signup_date AND DATE_ADD(c.signup_date, INTERVAL 30 DAY)
GROUP BY c.customer_id
HAVING SUM(s.watch_minutes) > 50 * 60
```

Helpfully, `code-davinci-002` is able to make inferences from variable names; for example, it infers that `watch_minutes` has units of minutes and therefore needs to be converted by a factor of 60 before being compared with 50 hours.

For easier prompting, you can also try `text-davinci-003`.