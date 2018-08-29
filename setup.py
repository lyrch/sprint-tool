import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()


setuptools.setup(
        name="sprint-tool",
        version="0.0.1",
        author="Jared Wilkerson",
        author_email="wilkerson.jared@gmail.com",
        description="A tool for managing Jira sprints",
        long_description=long_description,
        long_description_content_type="text/markdown",
        url="https://github.com/lyrch/sprint-tool",
        packages=setuptools.find_packages(),
        classifiers=("Programming Language :: Python :: 3"),
        entry_points = """
            [console_scripts]
            sprint-tool= sprint_tool.main:run
        """
)
