"""Manual smoke test for server.py. Not part of the pytest/unittest suite."""

import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

URL = "http://127.0.0.1:8787/mcp"


async def main():
    async with streamable_http_client(URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("tools:", [t.name for t in tools.tools])

            result = await session.call_tool(
                "write_file",
                {"project": "smoke-test", "content": "# MEMORY.md\nhello from smoke test\n"},
            )
            print("write_file:", result.content[0].text)

            result = await session.call_tool("read_file", {"project": "smoke-test"})
            print("read_file:", repr(result.content[0].text))

            result = await session.call_tool("list_files", {"project": "smoke-test"})
            print("list_files:", result.content[0].text)

            result = await session.call_tool("list_projects", {})
            print("list_projects:", result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
