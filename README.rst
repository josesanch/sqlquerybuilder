SQL Query Builder based on django ORM
=====================================

What's that?
-----------

Is a library that you can use to build sql queries if your are accustomed to use Django ORM


How to use
----------

There are 4 main objects Q, F, QuerySet and SQLModel.

Using it 
---------------

.. code-block:: python
   
   from sqlquerybuilder import SQLModel, Queryset, Q, F
   
   class Client(SQLModel):
       table = "clients"
                
       
   Client.objects.filter(name="Jhon").exclude(lastname="Doe").group_by("family")

   sql = Queryset("clients").filter(name="Jhon").exclude(lastname="Doe").group_by("family")

   
   sql = Client.objects.filter(Q(name="John") & ~Q(lastname="Doe"))
   
   sql.group_by("family")
                

   sql = Queryset("users")\
                .filter(nombre="jose")\
                .order_by( "nombre", "-fecha")\
                .filter(fecha__lte=F("now()"))[:10]

   
  "SELECT * FROM users WHERE ((nombre='jose') AND (fecha<=now())) ORDER BY nombre, fecha DESC LIMIT 10"
  
   
  str(sql) will result an string with the sql generated


