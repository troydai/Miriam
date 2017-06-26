## Miriam

Miriam run Azure CLI tests in parallel on Azure Batch.

### Design

Miriam will create two job. The first job build not only the Azure CLI product code but also its test code. 
The build result will be saved to a container.
The second job will prepare all the nodes
with the build created in the first job.
An then a job mananger task will schedule tasks for each individual test.

The product code repository hosts the build script and test script.
Miriam only creates job in Azure Batch.