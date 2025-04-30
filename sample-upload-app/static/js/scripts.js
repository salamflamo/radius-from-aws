// Empty JS for your own code to be here

$(function() {
    $('#btnCheckDb').(function() {
 
        $.ajax({
            url: '/main',
            data: $('form').serialize(),
            type: 'POST',
            success: function(response) {
                console.log(response);
            },
            error: function(error) {
                console.log(error);
            }
        });
    });
});