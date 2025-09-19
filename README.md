# Entrega N° 3 Cloud Computing

En este repositorio de encuentra el código de frontend y backend de la tercera entrega junto con la infraestructura como código creada usando CDK con Python.
Para probar la funcionalidad de la solución es necesario tener AWS CLI y CDK instalados, pero en la carpeta de infraestructura (/infra) se encuentran unos templates en formato JSON que contienen el CloudFormation que se puede subir manualmente a AWS (manualmente fue la única forma en la que pude hacerlo debido a las limitaciones de la cuenta de AWS Academy).
Para que funcione solo es necesario subir el template y el los outputs se entrega el DNS del Load Balancer que tiene la página funcionando.

Diagrama de Infraestructura usando EC2 para el frontend:

![BookStore Diagrams](https://github.com/user-attachments/assets/5163bb31-eed3-47e3-bc1b-2ad63c33642d)

## S3 para el Frontend (Rama S3-deploy)

Debido a las limitaciones de la cuenta AWS y el LabRole que es asignado, no es posible desde CDK hacer el deployment del frontend en el S3. La única solución a esto es desde CDK crear el S3 y manualmente subir el build del frontend al S3 (Esta es la solución implementada por mi parte). Si no se tuvieran las restricciones del laboratorio sería posible hacerlo como debería, pero si no existieran las restricciones la mejor opción sería usar CloudFront. Igualmente la solución es válida pero no tan automática como se espera.
