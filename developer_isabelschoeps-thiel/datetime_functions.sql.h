
- SQL code to load and define 'datetime' functions

- load the new functions

load '/home/dz/lib/postgres/datetime_functions.so';

- define the new functions in postgres

create function time_difference(time,time)
  returns time
  as '/home/dz/lib/postgres/datetime_functions.so' 
  language 'js';

create function currentDate()
  returns date
  as '/home/dz/lib/postgres/datetime_functions.so' 
  language 'js';

create function currentTime()
  returns time
  as '/home/dz/lib/postgres/datetime_functions.so' 
  language 'js';

create function hours(time)
  returns int4
  as '/home/dz/lib/postgres/datetime_functions.so' 
  language 'js';

create function minutes(time)
  returns int4
  as '/home/dz/lib/postgres/datetime_functions.so' 
  language 'js';

create function seconds(time)
  returns int4
  as '/home/dz/lib/postgres/datetime_functions.so' 
  language 'js';

create function day(date)
  returns int4
  as '/home/dz/lib/postgres/datetime_functions.so'
  language 'js';

create function month(date)
  returns int4
  as '/home/dz/lib/postgres/datetime_functions.so'
  language 'js';

create function year(date)
  returns int4
  as '/home/dz/lib/postgres/datetime_functions.so'
  language 'js';

create function asMinutes(time)
  returns int4
  as '/home/dz/lib/postgres/datetime_functions.so' 
  language 'js';

create function asSeconds(time)
  returns int4
  as '/home/dz/lib/postgres/datetime_functions.so' 
  language 'js';

create operator - (
  leftarg=time, 
  rightarg=time, 
  procedure=time_difference);

