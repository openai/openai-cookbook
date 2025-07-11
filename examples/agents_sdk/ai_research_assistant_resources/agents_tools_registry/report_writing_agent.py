from agents import Agent, Runner, RunConfig


class ReportWritingAgent:
    _DEFAULT_NAME = "Report Writing Agent"

    # NOTE: Double braces around RESOURCES so that str.format leaves them intact when formatting other placeholders.
    REPORT_WRITER = """You are a report writer that that writes a detailed report in Markdown file format on a report outline \
                            provided by the user citing sources in <REFERENCE RESOURCES>. Use a formal tone. 

                            Follow the following rules: 

                            1. Take your time to analyze the topic provided by the user, and review all the sources provided in REFERENCE RESOURCES.

                            2. Do you own synthesis of sources presented in REFERENCE RESOURCES. Draw conclusions from the sources. 

                            3. For each section of the report write 2 to 3 paragraphs using as many REFERENCE RESOURCES as applicable. 

                            4. Use Markdown header # for title, ## for section header, and ### for detailed content in the sections. Keep detailed \
                            sections to between 6 and 10.  

                            5. Cite sources that you use from REFERENCE RESOURCES in <source></source> tags. You don't need to provide title of the \
                            source.
                            
                            For example: 
                            Robust integration within Apple's ecosystem, set it apart from competitors 
                            <source>https://618media.com/en/blog/apple-vision-pro-vs-competitors-a-comparison</source>

                            6. Do not include any additional sources not provided in REFERENCE RESOURCES below. 

                            The resources are provide in a JSON format below:

                            <REFERENCE RESOURCES> 
                            {{{RESOURCES}}}
                            </REFERENCE RESOURCES> 
                            """

    def __init__(
        self,
        research_resources: str,
        *,
        model: str = "o3",
        tools: list | None = None,
        name: str | None = None,
        instructions: str | None = None,
    ) -> None:
        """Create an agent capable of writing a detailed Markdown report.

        Parameters
        ----------
        research_resources: str
            A string containing reference resources (e.g., URLs, snippets) that will be injected into the default
            prompt, replacing the ``{{{RESOURCES}}}`` placeholder.
        model: str, optional
            Name of the model to use. Defaults to ``"o3"``.
        tools: list, optional
            Optional list of tools to pass into the underlying ``agents.Agent``.
        name: str, optional
            Custom name for the agent instance.
        instructions: str, optional
            If provided, these instructions override the default prompt.
        """

        # ------------------------------------------------------------------
        # Handle different input formats for `research_resources`.
        # If a string is provided, we use it directly; otherwise, convert JSON
        # objects (list / dict) into the required Markdown-friendly string.
        # ------------------------------------------------------------------

        resources_str: str = research_resources

        # Use custom instructions if supplied, otherwise format the template with the given resources.
        formatted_instructions = instructions or self.REPORT_WRITER.replace(
            "{{{RESOURCES}}}", resources_str
        )

        self._agent = Agent(
            name=name or self._DEFAULT_NAME,
            instructions=formatted_instructions,
            tools=tools or [],
            model=model,
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def agent(self) -> Agent:  # type: ignore[name-defined]
        """Return the underlying :class:`agents.Agent` instance."""
        return self._agent

    async def task(self, outline: str) -> str:
        """Generate a Markdown report based on the provided outline.

        Parameters
        ----------
        outline: str
            The outline or prompt describing the desired report structure.

        Returns
        -------
        str
            A Markdown formatted report following the provided outline and referencing the supplied resources.
        """

        cfg = RunConfig(tracing_disabled=True)
        result = await Runner.run(self._agent, outline, run_config=cfg)
        return result.final_output 