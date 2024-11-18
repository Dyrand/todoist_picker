from flask import Flask, render_template, request
from todoist_api_python.api import TodoistAPI
import random
import os

from . import constants
from . import db

database_name = "choices.sqlite"

app = Flask(__name__)
app.config.from_mapping(
     DATABASE = database_name
)
db.init_app(app)

if not os.path.exists(database_name):
    with app.app_context():
        db.init_db()

todoist_api = TodoistAPI(constants.TODOIST_API_KEY)

class ChoiceItem():
    def __init__(self,name,id,weight,type_of=""):
        self.id = id
        self.name = name
        self.weight = weight
        self.type_of = type_of
        self.parent = None
        self.sub_choices = {}
    
    def set_parent(self,parent):
        self.parent = parent

    def add_sub_choice(self,sub_choice):
        sub_choice.set_parent(self)
        self.sub_choices[sub_choice.id] = sub_choice

    def calc_choices_weight_sum(self):
        current_sum = 0
        for choice in self.sub_choices.values():
            current_sum += choice.weight
        return current_sum

    def pick_sub_choice(self):
        weights = [sub_choice.weight for sub_choice in self.sub_choices.values()]
        choice = random.choices(list(self.sub_choices.values()),weights,k=1)
        return choice[0]
    
    def pick_sub_choice_recursive(self):
        choice = self
        # result = []
        try:
            while True:
                choice = choice.pick_sub_choice()
                # result.append(choice.name)
        except Exception as e:
            pass

        return choice
    
    def get_flat_name(self):
        result = [self.name]
        reference = self
        try:
            while True:
                reference = reference.parent
                result.insert(0,reference.name)
        except Exception as e:
            pass
        
        result.pop(0)

        return result
    
    def get_rarity(self):
        flat_probabiltiy = self.get_flat_probabiltiy()
        if flat_probabiltiy == 0:
            return "rarity_0"
        elif flat_probabiltiy > 10**-1:
            return "rarity_1"
        elif flat_probabiltiy > 10**-2:
            return "rarity_2"
        elif flat_probabiltiy > 10**-3:
            return "rarity_3"
        elif flat_probabiltiy > 10**-4:
            return "rarity_4"
        elif flat_probabiltiy > 10**-5:
            return "rarity_5"
        else:
            return "rarity_6"

    def get_probability(self):
        try:
            return self.weight/self.parent.calc_choices_weight_sum()
        except Exception as e:
            return 1
        
    def get_flat_probabiltiy(self):
        probabiltiy = 1
        reference = self
        try:
            while True:
                probabiltiy *= reference.get_probability()
                reference = reference.parent
        except Exception as e:
            pass

        return probabiltiy
    
    def get_flat_probability_formatted(self):
        probability = self.get_flat_probabiltiy()
        return f"{probability*100:.3f}%"

    def get_item(self,name):
        try:
            return self.sub_choices[name]
        except Exception as e:
            return None

    class iterator:
        def __init__(self, choice_item):
            self.choice_item = choice_item
            self.next_iter_stack = []

            try:
                self.next_iter_stack.append(list(self.choice_item.sub_choices.values()).__iter__())
            except Exception as e:
                self.next_item_iter = [].__iter__()

        def __next__(self):
            while len(self.next_iter_stack):
                try:
                    next_item = self.next_iter_stack[-1].__next__()
                    if next_item.sub_choices:
                        self.next_iter_stack.append(list(next_item.sub_choices.values()).__iter__())
                    return next_item
                except StopIteration as e:
                    self.next_iter_stack.pop()
                
            raise StopIteration            

    def __iter__(self):
        return ChoiceItem.iterator(self)


class TodoProject(ChoiceItem):
    def __init__(self, name, id, weight):
        super().__init__(name,id,weight,"project")
        self.sections = {}
        self.tasks = {}

    def add_section(self, section):
        self.sections[section.id] = section
        self.add_sub_choice(section)

    def add_task(self, task):
        self.tasks[task.id] = task
        self.add_sub_choice(task)

class TodoSection(ChoiceItem):
    def __init__(self, name, id, weight):
        super().__init__(name,id,weight,"section")
        self.tasks = {}

    def add_task(self, task):
        self.tasks[task.id] = task
        self.add_sub_choice(task)

class TodoTask(ChoiceItem):
    def __init__(self, content, id, weight):
        super().__init__(content,id,weight,"task")
        self.content = content


@app.route("/")
def main_page():
    ignore_names = ["Inbox"]

    base_weight = 50
    
    projects = todoist_api.get_projects()

    head_choice = ChoiceItem("head",0,100)
    
    db_s = db.get_db()

    for project in projects:
        if project.name not in ignore_names:
            head_choice.add_sub_choice(TodoProject(project.name,project.id,base_weight))
            
    sections = todoist_api.get_sections()

    for section in sections:
        project = head_choice.get_item(section.project_id)
        project.add_section(TodoSection(section.name,section.id,base_weight))

    tasks = todoist_api.get_tasks() 
    
    for task in tasks:
        if task.parent_id == None:
            project = head_choice.get_item(task.project_id)
            todo_task = TodoTask(task.content,task.id,base_weight)
            if task.section_id != None:
                section = project.get_item(task.section_id)
                section.add_task(todo_task)
            else:
                project.add_task(todo_task)
        else:
            #specify type as sub_task
            res = db_s.execute(f"""UPDATE choices
                                   SET type_of = 'sub_task'
                                   WHERE id = ?""",(task.id,))
    
    current_id_list = []

    for item in head_choice:
        current_id_list.append(item.id)
        res = db_s.execute(f'SELECT * FROM choices where id == ?',(item.id,))
        data = res.fetchone()
        if data != None:
            item.weight = data["choice_weight"]
            db_s.execute(f"""UPDATE choices
                             SET parent_id = ?, choice_name = ?
                             WHERE id = ?""",
                             (item.parent.id,item.name,item.id))
        else:
            db_s.execute(f'INSERT INTO choices VALUES (?,?,?,?,?)',
                         (item.id,item.type_of,item.parent.id,item.name,item.weight))
    
    db_s.execute(f'DELETE FROM choices WHERE id NOT IN ({','.join(current_id_list)})')

    db_s.commit()

    return render_template(
        "app.html",
        choice_items=head_choice.sub_choices
    )

@app.route('/make_choice', methods=['GET'])
def make_choice():
    head_choice = ChoiceItem("head",0,100)

    db_s = db.get_db()
    res = db_s.execute('SELECT * FROM choices where type_of == "project"')
    data = res.fetchall()

    parent_id_lookup = {}

    # names = [description[0] for description in res.description]
    # print(data)
    for project in data:
        choice = TodoProject(project['choice_name'],project['id'],project['choice_weight'])
        head_choice.add_sub_choice(choice)
        parent_id_lookup[project['id']] = choice

    res = db_s.execute('SELECT * FROM choices where type_of == "section"')
    data = res.fetchall()
    for section in data:
        choice = TodoSection(section['choice_name'],section['id'],section['choice_weight'])
        project = head_choice.get_item(section["parent_id"])
        project.add_sub_choice(choice)
        parent_id_lookup[section['id']] = choice
    
    res = db_s.execute('SELECT * FROM choices where type_of == "task"')
    data = res.fetchall()
    for task in data:
        choice = TodoTask(task['choice_name'],task['id'],task['choice_weight'])
        parent_id = task["parent_id"]
        parent = parent_id_lookup[parent_id]
        parent.add_sub_choice(choice)
        
    result = head_choice.pick_sub_choice_recursive()
    flat_name = result.get_flat_name()
    rarity = result.get_rarity()

    return {"result":flat_name,"rarity":rarity,"id":result.id}

@app.route('/save_weights', methods=['PUT'])
def save_weight():
    db_s = db.get_db()
    req = request.get_json()
    for id, value in req.items():
        db_s.execute(f"""UPDATE choices
                         SET choice_weight = ?
                         WHERE id = ?""",
                         (value,id))

    db_s.commit()
    return {}