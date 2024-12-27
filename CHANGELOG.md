## 1.2.0 (2024-12-27)

### Feat

- **oltp**: add helper mixing to work with traces

## 1.1.0 (2024-12-23)

### Feat

- **workers**: add opentelemetry support to taskiq

## 1.0.0 (2024-11-28)

### Feat

- **workers**: add progress reporting
- **utils**: add new methods to dict_utils (get_object, set_objects)

### Refactor

- **utils**: rename package `utils.types` -> `utils.type_utils`

## 0.7.0 (2024-11-28)

### Feat

- **taskiq**: add middleware to maintain current task information in DI context
- **workers**: add task information in DI context
- **logging**: add filter for logging security context
- **logging**: add `with_logging_context` utility
- add security context support

## 0.6.2 (2024-10-27)

### Fix

- **taskiq**: add scheduler support
- **lock**: fix bug in async version of wait_and_acquire

## 0.6.1 (2024-10-27)

### Fix

- **taskiq**: fix initialization behaviour

## 0.6.0 (2024-10-26)

### Feat

- **lock**: add with_lock context manager

## 0.5.0 (2024-10-26)

### Feat

- **lock**: add lock service
- **django**: add abstract model meta

## 0.4.0 (2024-10-17)

### Feat

- **workers**: add initial taskiq support

## 0.3.0 (2024-10-11)

### Feat

- **di**: make django di module async compatible

## 0.2.0 (2024-10-07)

### Feat

- **di**: add di support to django admin

## 0.1.0 (2024-10-05)
