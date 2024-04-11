from openai import OpenAI
import anthropic
from torch import bfloat16
import transformers
import subprocess
import re

class Agent():
    def __init__(self,
                model_name,os, commands, output_format,
                api_key=None):
        self.model_name=model_name
        self.api_key=api_key
        self.os=os
        self.commands=commands
        self.output_format=output_format
        self.done=False
        self.system_prompt=self.create_system_prompt()
        self.model=self.create_model_instance()
        self.context=None #The memory
    def create_model_instance(self):
        if self.model_name=="GPT4":
            client = OpenAI(api_key=self.api_key)
        elif self.model_name=='Claude':
            client = anthropic.Anthropic(api_key=self.api_key)
        elif self.model_name=='mixtral':
            model = transformers.AutoModelForCausalLM.from_pretrained(model_id, trust_remote_code=True,torch_dtype=bfloat16,device_map='auto')
            model.eval()
            tokenizer = transformers.AutoTokenizer.from_pretrained(model_id)
            client = transformers.pipeline(
                model=model, tokenizer=tokenizer,
                return_full_text=False,  # if using langchain set True
                task="text-generation",
                temperature=0.1,  # 'randomness' of outputs, 0.0 is the min and 1.0 the max
                top_p=0.15,  # select from top tokens whose probability add up to 15%
                top_k=0,  # select from top 0 tokens (because zero, relies on top_p)
                max_new_tokens=512,  # max number of tokens to generate in the output
                repetition_penalty=1.1  # if output begins repeating increase
            )
        return client
    def create_system_prompt(self):
        command=', or '.join (self.commands)
        prompt="You are a software building assistant. Generate a .sh script to run in " +self.os+", that builds the latest version of any given software. The script should either use "+ command+" to build the software, and test the built software. The output of the script should be 'success' or 'fail'. If the test fails, log all output to error.log. Do not describe any of the process. Only display the code for the .sh script file in "+self.output_format+" format. When an error just give the new scripts, not the old script. Do not suggest editing system files."
        return prompt
    def extract_executables(self, text):
    # Regular expression pattern to match executable code blocks
        pattern = r"```(?:\w+)?\n(.*?)```"

    # Extract executable code blocks from the text
        exec_blocks = re.findall(pattern, text, re.DOTALL)

        return exec_blocks
    def evaluate(self, result):
        if result.returncode==0:
            self.done=True
        elif "fail" in result.stdout:
            self.context.append({"role": "user", "content": result.stdout})
            content=result.stdout
            self.done=False
        else:
            self.done=True
    def execute(self):
        shell_script_command = "./test.sh"
        try:
            result=subprocess.run(shell_script_command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.evaluate(result)
        except subprocess.CalledProcessError as e:
            self.done=False
            content=str(e)
            print("Error:", content)
            self.context.append({"role": "user", "content": content})
    def init_context(self):
        if self.model_name=="GPT4":
            context=[{"role": "system", "content": self.system_prompt},]
        elif self.model_name=='Claude':
            context=[]
        elif self.model_name=='mixtral':
            context = [
                {"role": "user", "content": self.system_prompt},
                {"role": "assistant", "content": "Sounds great!"}
                ]
        return context
    def mixtral_exec(self, text):
        prompt = self.model.tokenizer.apply_chat_template(self.context, tokenize=False, add_generation_prompt=True)
        outputs = self.model(prompt, max_new_tokens=1000, do_sample=True, temperature=0.7, top_k=50, top_p=0.95)
        text=outputs[0]['generated_text']
        return text
    def gpt(self, text):
        completion = self.model.chat.completions.create(
          model="gpt-4",
          messages=context
        )
        text=completion.choices[0].message.content
        return text 
    def anthropic(self, text):
        message = self.model.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=3934,
            temperature=0.0,
            system=self.system_prompt,
            messages=self.context
            )
        print(message)
        text=message.content[0].text
        return text
    def llm(self, software):
        self.done=False
        self.context=self.init_context()
        text="Install "+software
        self.context.append({"role": "user", "content": text})
        trials=0
        while not self.done and trials <10:
            if self.model_name=="GPT4":
                text=self.gpt(text)
            elif self.model_name=='Claude':
                text=self.anthropic(text)
            elif self.model_name=='mixtral':
                text=self.mixtral_exec(text)
            self.context.append({"role": "assistant", "content": text})
            i=self.extract_executables(text)
            file_path = "test.sh"
            if len(i)>0:
                with open(file_path, "w") as file:
                    file.write(i[0])
                self.execute()
            trials+=1
key="None"
output="```"
commands=['sudo apt', 'pip', 'Download']
agent=Agent("Claude", "Ubuntu", commands, output, api_key=key)
agent.llm("Numpy")
