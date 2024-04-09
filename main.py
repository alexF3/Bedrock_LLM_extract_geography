import boto3
import json
import pandas as pd
import os
import time


from pydantic import BaseModel
from pydantic import validator
import re

# Load all 24k unique listed "first affiliations" for authors in JAMA articles 2013-2023 
# (source: PubMed .nbib file)
df = pd.read_csv('jama_all_2013_2023_24k.csv')
print(df.head())


class Aff(BaseModel):
    city: str
    state: str
    nation: str
    
    @validator('city')
    def validate_city(cls, v):
        if len(v) > 30:
            raise ValueError('City must be less than 25 characters')
        if not re.match(r'^[a-zA-Z-\s]+$', v):
            raise ValueError('City contains invalid characters')
        return v
    
    @validator('state')
    def validate_state(cls, v):
        if len(v) > 40:
            raise ValueError('State must be less than 25 characters')
        if not re.match(r'^[a-zA-Z-]+$', v):
            raise ValueError('State contains invalid characters')
        return v
    
    @validator('nation')
    def validate_nation(cls, v):
        if len(v) > 40:
            raise ValueError('Nation must be less than 25 characters')
        if not re.match(r'^[a-zA-Z-\s]+$', v):
            raise ValueError('Nation contains invalid characters')
        return v


bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')

def runModel(input_affiliation):
    # Note: this prompt does not conform strictly to Mistral's suggested format
  prompt = f"Separate the affiliation by the initials in parentheses. Then get the nation, city, and state of each affiliation. Return the results in a JSON like \\n    \\\"{{\\\"affiliation\\\":\\\"from the second building on the third block at yale university, new haven, ct\\\",\\\"city\\\":\\\"new haven\\\", \\\"state\\\":\\\"ct\\\",\\\"nation\\\":\\\"usa\\\"}}\\\"\\nReturn only formatted JSON. If you do not know the nation, return \\\"unknown\\\". If you do not know the state, return \\\"unknown\\\". If you do not know the city, return \\\"unknown\\\".\\nExamples: \\n1. user: \\\"columbia university, new york, NY\\\"\\n\\\"{{\\\"affiliation\\\":\\\"columbia university, new york, NY\\\",\\\"city\\\":\\\"new york\\\",\\\"state\\\":\\\"ny\\\",\\\"nation\\\":\\\"usa\\\"}}\\\"\\n2. user: \\\"department of psychiatry, university of california, san francisco.\\\"\\n\\\"{{\\\"affiliation\\\":\\\"department of psychiatry, university of california, san francisco.\\\",\\\"city\\\":\\\"san francisco\\\",\\\"state\\\":\\\"ca\\\",\\\"nation\\\":\\\"usa\\\"}}\\\"\\n3. user: \\\"a colony on mars\\\"\\n\\\"{{\\\"affiliation\\\":\\\"a colony on mars\\\",\\\"city\\\":\\\"unknown\\\",\\\"state\\\":\\\"unknown\\\",\\\"nation\\\":\\\"unknown\\\"}}\\\"\\nReturn only valid JSON and do not include any punctuation. Always include affiliation, city, state, and nation.\\naffiliation: {input_affiliation}"
  payload = {
    "prompt": prompt,
    "max_tokens": 400,
    "top_k": 90,
    "top_p": 0.3,
    "stop": [],
    "temperature": 0.0
  }
  
  raw_response = bedrock_runtime.invoke_model(
    modelId='mistral.mistral-7b-instruct-v0:2',
    body=json.dumps(payload)
  )
  
  body = raw_response["body"].read().decode("utf-8")
  
  
  response_body = json.loads(body)
  outputs = response_body["outputs"]
  
  location = outputs[0]["text"] 
  return(location)
  
  
def getGeography(affiliation):
    """ Have thee LLM  make up to 3 attempts to extract city, state, and nation from the affiliation 
    and return a JSON like:
    {
        "affiliation": "from the second building on the third block at yale university, new haven, ct",
        "city": "new haven",
        "state": "ct",
        "nation": "usa"
    }
    If the return is not valid, return the final attempt.
 

    Args:
        affiliation (str): first affiliation listed for an author
    """    
    tries = 0
    while tries < 3:
        result =  runModel(affiliation)
        result =  result.replace("\\'",'')
        tries+=1

        try:
            result = re.sub(r"\\", "", result)
            result = result.replace('\n','')
            try:
              pattern = r'\{(.*?)\}'
              result = '{'+re.search(pattern, result).group(1)+'}'
            except:
              pass
            print(result)
            data = Aff.model_validate_json(result)
            print('GOOD!')
            return(result)
        except ValueError as e:
            print('{} invalid: {}'.format(tries,result))
            print(e.errors())
            pass

    print("bad response:")
    print('result: {}'.format(result))
    return(runModel(affiliation))
    
###
# Run the model on all of the unique author affiliations in the dataset
# Note: I got security token expiration errors consistently when attempting to apply the function to the pandas dataframe.
# ...for some reason looping does not produce the same error.
start = time.time()

entries_list = []
bad_list = []
ct = 0
for row in df.itertuples():
    entry = {
        'firstAffiliation':row.firstAffiliation,
        'geography':getGeography(row.firstAffiliation)
    }
    entries_list.append(entry)
    ct+=1
    if ct%50==0:
        pd.DataFrame(entries_list).to_csv('all_jama_2013_2023_mistral_pydantic_24k.csv',index=False)
    

duration = time.time() - start
print('Total minutes of processing: {}'.format(duration/60))
df.to_csv('JAMA_all_pydantic_mystral_24k.csv',index=False)