"""Generate the Jenkins matrix from the existing release contract."""
import json
import re
from release_contract import TARGETS


def plan(targets=TARGETS):
    result = [{'name': 'Loader-neutral core and Java 8/25 runtime tests', 'java': 17,
               'command': './gradlew :core:build :core:testJava8 :core:testJava25 --no-daemon --max-workers=1\n'
                          'python3 tools/release_contract.py jar --target core --directory core/build/libs'}]
    for target in targets:
        name = target['target']
        java = int(target['java'])
        if not re.fullmatch(r'[a-z]+-[0-9]+(?:\.[0-9]+)*', name) or java not in (8, 17, 21, 25):
            raise ValueError('Unsupported target or pinned build runtime')
        result.append({'name': name, 'java': java,
                       'command': f'(cd targets/{name} && ./gradlew build --no-daemon --max-workers=1 --stacktrace)\n'
                                  f'python3 tools/release_contract.py jar --target {name} --directory targets/{name}/build/libs'})
    return result


if __name__ == '__main__':
    print(json.dumps(plan()))
