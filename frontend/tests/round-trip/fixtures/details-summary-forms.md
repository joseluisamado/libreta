## Review questions

<details><summary>Diagram source</summary>

```text
client -> proxy -> server
```

</details>

<details><summary>Short answer</summary>

Use a queue between the two services.

<details><summary>Long answer</summary>

- The producer never waits for the consumer.
- Retries live in one place.

</details></details>

<details>
<summary><b>Response fields</b>: the ones the answer <i>relies</i> on, with <code>status</code></summary>

The body is ignored.

</details>

<details name="steps" open><summary><strong>Step 1</strong></summary>

Install it.

</details>
