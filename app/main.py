import argparse
import sys

from openai import OpenAI

from app.config import API_KEY, BASE_URL
from app.agent import run_agent_loop


def main():
    p = argparse.ArgumentParser()
    p.add_argument("-p", required=True)
    args = p.parse_args()

    if not API_KEY:
        sys.exit("Error: API Key is not set.")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    logo = r"""
                    █████╗ ██╗       █████╗   ██████╗ ███████╗███╗   ██╗████████╗
                    ██╔══██╗██║      ██╔══██╗ ██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
                    ███████║██║      ███████║ ██║  ███╗█████╗  ██╔██╗ ██║   ██║
                    ██╔══██║██║      ██╔══██║ ██║   ██║██╔══╝  ██║╚██╗██║   ██║
                    ██║  ██║███ ██║  ██║ ╚██████╔╝███████╗██║ ╚████║   ██║
                    ╚═╝  ╚═╝╚══════╝ ╚═╝  ╚═╝  ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝

                                            by Suman
     """
    print(logo)

    run_agent_loop(client, args.p)


if __name__ == "__main__":
    main()
